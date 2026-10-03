#!/usr/bin/env python3
"""
小红书图文生成工具 - Web 版本
Flask 后端服务
"""

import json
import asyncio
import base64
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import zipfile
import io

from main import summarize_to_slides, render_html, capture_slides, extract_images_from_markdown, filter_valid_images
from sensitive_words import detect_sensitive_words, highlight_sensitive_words, get_sensitive_words_by_category
import ai_providers

app = Flask(__name__)

# AI 错误分类 -> HTTP 状态码。未识别的分类一律 502，
# 不用 500 掩盖真实的外部服务故障。
_AI_ERROR_STATUS = {
    'missing_api_key': 400,
    'unknown_provider': 400,
    'bad_request': 400,
    'auth_failed': 401,
    'insufficient_balance': 402,
    'model_not_found': 404,
    'quota_exhausted': 429,
    'rate_limited': 429,
    'timeout': 504,
    'network': 502,
    'service_unavailable': 502,
    'bad_response': 502,
    'empty_response': 502,
    'truncated': 502,
}


def _status_for_ai_error(exc):
    return _AI_ERROR_STATUS.get(exc.code, 502)


def _ai_error_response(exc):
    return jsonify(exc.to_dict()), _status_for_ai_error(exc)


@app.route('/api/ai-config', methods=['GET'])
def get_ai_config():
    """返回提供商清单与当前选择。只回显脱敏 Key，不返回明文。"""
    try:
        saved = ai_providers.load_config()
        return jsonify({
            'success': True,
            'active_provider': saved['provider'],
            'providers': ai_providers.provider_public_info(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-config', methods=['POST'])
def update_ai_config():
    """保存当前提供商/模型与 API Key。空 Key 表示沿用已保存值。"""
    try:
        data = request.json or {}
        provider = data.get('provider')
        if provider not in ai_providers.PROVIDERS:
            return jsonify({'error': f'未知提供商：{provider}'}), 400

        saved = ai_providers.load_config()
        saved['provider'] = provider

        model = (data.get('model') or '').strip()
        if model:
            saved['models'][provider] = model

        api_key = (data.get('api_key') or '').strip()
        if api_key:
            saved['api_keys'][provider] = api_key
        elif data.get('clear_key'):
            saved['api_keys'].pop(provider, None)

        ai_providers.save_config(saved)
        return jsonify({
            'success': True,
            'active_provider': saved['provider'],
            'providers': ai_providers.provider_public_info(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-test', methods=['POST'])
def test_ai_config():
    """用最小生成请求验证 Key + 模型 + 配额，不落盘。"""
    try:
        data = request.json or {}
        provider = data.get('provider') or ai_providers.active_provider()
        result = ai_providers.test_connection(
            provider,
            api_key=(data.get('api_key') or '').strip() or None,
            model=(data.get('model') or '').strip() or None,
        )
        return jsonify({'success': True, **result})
    except ai_providers.AIProviderError as e:
        return _ai_error_response(e)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai-models', methods=['POST'])
def list_ai_models():
    """查询上游实际可用模型，失败时回退到内置清单"""
    try:
        data = request.json or {}
        provider = data.get('provider') or ai_providers.active_provider()
        api_key = (data.get('api_key') or '').strip() or None
        try:
            models = ai_providers.list_remote_models(provider, api_key=api_key)
            return jsonify({
                'success': True,
                'provider': provider,
                'models': models,
                'source': 'remote',
                'selected': ai_providers.get_model(provider),
            })
        except ai_providers.AIProviderError as e:
            print(f"⚠️  {provider} 模型列表拉取失败（{e.code}）：{e}")
            return jsonify({
                'success': False,
                'provider': provider,
                'models': ai_providers.PROVIDERS[provider]['models'],
                'source': 'fallback',
                'code': e.code,
                'fallback_reason': str(e),
                'selected': ai_providers.get_model(provider),
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """生成图片 API"""
    try:
        data = request.json
        content = data.get('content', '')
        style = data.get('style', 'xiaohongshu')  # 预留风格参数
        
        if not content or len(content.strip()) < 50:
            return jsonify({'error': '内容太短，请输入至少 50 字'}), 400
        
        print(f"🤖 调用 AI 生成内容 (风格: {style})")
        
        # 调用 AI 生成幻灯片内容
        slides_data = summarize_to_slides(content)
        
        # 渲染 HTML（传递风格参数）
        html_content = render_html(slides_data, style)
        
        # 截图生成图片
        output_files = asyncio.run(capture_slides(html_content))
        
        # 读取图片并转为 base64
        images = []
        for filepath in output_files:
            with open(filepath, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
                images.append({
                    'filename': Path(filepath).name,
                    'data': f'data:image/png;base64,{img_data}'
                })
        
        return jsonify({
            'success': True,
            'slides_data': slides_data,
            'images': images,
            'count': len(images)
        })
        
    except ai_providers.AIProviderError as e:
        return _ai_error_response(e)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/preview', methods=['POST'])
def preview():
    """预览模式：只调用 AI 生成内容，不渲染图片
    支持 Markdown 格式输入，自动提取图片并智能分配
    """
    try:
        data = request.json
        content = data.get('content', '')
        
        if not content or len(content.strip()) < 50:
            return jsonify({'error': '内容太短，请输入至少 50 字'}), 400
        
        print(f"🤖 调用 AI 生成内容（预览模式）")
        
        # 解析 Markdown，提取图片
        text_content, image_urls = extract_images_from_markdown(content)
        
        # 过滤有效图片（跳过 GIF，验证可访问性）
        valid_images = []
        if image_urls:
            print(f"📷 发现 {len(image_urls)} 张图片，正在验证...")
            valid_images = filter_valid_images(image_urls)
            print(f"✅ {len(valid_images)} 张图片验证通过")
            if len(image_urls) - len(valid_images) > 0:
                print(f"⚠️ {len(image_urls) - len(valid_images)} 张图片被跳过（GIF 或无法访问）")
        
        # 调用 AI 生成幻灯片内容（传入有效图片列表）
        slides_data = summarize_to_slides(text_content, valid_images if valid_images else None)
        
        return jsonify({
            'success': True,
            'slides_data': slides_data,
            'extracted_images': valid_images,  # 返回提取的图片列表供前端参考
            'image_count': len(valid_images)
        })
        
    except ai_providers.AIProviderError as e:
        return _ai_error_response(e)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/render', methods=['POST'])
def render():
    """渲染模式：使用已有的 JSON 数据渲染图片"""
    try:
        data = request.json
        slides_data = data.get('slides_data')
        style = data.get('style', 'xiaohongshu')
        
        if not slides_data:
            return jsonify({'error': '缺少幻灯片数据'}), 400
        
        print(f"🎨 渲染图片 (风格: {style})")
        
        # 渲染 HTML
        html_content = render_html(slides_data, style)
        
        # 截图生成图片
        output_files = asyncio.run(capture_slides(html_content))
        
        # 读取图片并转为 base64
        images = []
        for filepath in output_files:
            with open(filepath, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
                images.append({
                    'filename': Path(filepath).name,
                    'data': f'data:image/png;base64,{img_data}'
                })
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/regenerate-slide', methods=['POST'])
def regenerate_slide():
    """重新生成单张幻灯片内容"""
    try:
        data = request.json
        slide_index = data.get('slide_index')  # 0 表示封面，1+ 表示内容页
        original_content = data.get('original_content', '')  # 原始长文
        current_slides_data = data.get('slides_data')
        
        if slide_index is None or not current_slides_data:
            return jsonify({'error': '缺少必要参数'}), 400
        
        print(f"🔄 重新生成第 {slide_index} 张幻灯片")
        
        if slide_index == 0:
            # 重新生成封面
            current_title = current_slides_data.get('cover_title', '')
            current_subtitle = current_slides_data.get('cover_subtitle', '')
            current_tags = current_slides_data.get('cover_tags', [])
            
            prompt = f"""你是一个专业的内容编辑，擅长创作小红书风格的封面。

【任务】重新生成封面，保持相同主题，但使用不同的表达方式。

【当前封面内容】
- 标题：{current_title}
- 副标题：{current_subtitle}
- 标签：{current_tags}

【要求】
1. 主题必须与当前封面一致（围绕"{current_title}"这个主题）
2. 用不同的角度、不同的表达方式重新阐述
3. 标题要吸引眼球，使用小红书风格的表达（10字以内）
4. 副标题用一句话概括文章主旨
5. 标签要与主题相关，3-5个，每个3-6字

【输出格式】JSON：
{{
    "cover_title": "新的封面大标题（简短有力，10字以内）",
    "cover_subtitle": "新的封面副标题（一句话概括文章主旨）",
    "cover_tags": ["标签1", "标签2", "标签3"]
}}

只输出 JSON，不要其他内容。"""
        else:
            # 重新生成内容页
            slide_idx = slide_index - 1
            current_slide = current_slides_data.get('slides', [])[slide_idx] if slide_idx < len(current_slides_data.get('slides', [])) else {}
            
            # 获取当前页面的标题和内容，作为主题参考
            current_title = current_slide.get('title', '')
            current_content = current_slide.get('content', [])
            current_content_text = '\n'.join([f"- {item}" for item in current_content])
            
            prompt = f"""你是一个专业的内容编辑，擅长创作小红书风格的内容页。

【任务】重新生成第 {slide_index} 张内容页，保持相同主题，但使用不同的表达方式。

【当前页面内容】
标题：{current_title}
要点：
{current_content_text}

【要求】
1. 主题必须与当前页面一致（围绕"{current_title}"这个主题）
2. 用不同的角度、不同的表达方式重新阐述相同的核心信息
3. 可以调整要点的顺序、合并或拆分要点
4. 标题可以换一种说法，但主题不变
5. 每个要点控制在 35 字以内
6. 内容要有信息量，不要空泛

【输出格式】JSON：
{{
    "title": "新的幻灯片标题（8字以内，主题与原标题一致）",
    "content": ["要点1", "要点2", "要点3", "要点4"]
}}

只输出 JSON，不要其他内容。"""
        
        try:
            raw_text = ai_providers.generate_json(prompt, temperature=0.9)
        except ai_providers.AIProviderError as e:
            print(f"❌ AI 调用出错 [{e.code}]: {e.detail or e}")
            return jsonify(e.to_dict()), _status_for_ai_error(e)
        
        new_content = json.loads(raw_text)
        
        # 更新 slides_data
        if slide_index == 0:
            current_slides_data['cover_title'] = new_content.get('cover_title', current_slides_data.get('cover_title'))
            current_slides_data['cover_subtitle'] = new_content.get('cover_subtitle', current_slides_data.get('cover_subtitle'))
            current_slides_data['cover_tags'] = new_content.get('cover_tags', current_slides_data.get('cover_tags'))
        else:
            slide_idx = slide_index - 1
            if slide_idx < len(current_slides_data.get('slides', [])):
                # 只更新 title 和 content，保留原有的 image 字段
                original_image = current_slides_data['slides'][slide_idx].get('image')
                current_slides_data['slides'][slide_idx]['title'] = new_content.get('title', current_slides_data['slides'][slide_idx].get('title'))
                current_slides_data['slides'][slide_idx]['content'] = new_content.get('content', current_slides_data['slides'][slide_idx].get('content'))
                # 保留图片（如果有的话）
                if original_image:
                    current_slides_data['slides'][slide_idx]['image'] = original_image
        
        return jsonify({
            'success': True,
            'slides_data': current_slides_data,
            'regenerated_index': slide_index
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/regenerate-style', methods=['POST'])
def regenerate_style():
    """使用已有的 JSON 数据重新生成不同风格的图片"""
    try:
        data = request.json
        slides_data = data.get('slides_data')
        style = data.get('style', 'xiaohongshu')
        
        if not slides_data:
            return jsonify({'error': '缺少幻灯片数据'}), 400
        
        print(f"🎨 切换风格到: {style} (不调用 AI，使用已有数据)")
        
        # 使用已有数据渲染新风格的 HTML
        html_content = render_html(slides_data, style)
        
        # 截图生成图片
        output_files = asyncio.run(capture_slides(html_content))
        
        # 读取图片并转为 base64
        images = []
        for filepath in output_files:
            with open(filepath, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
                images.append({
                    'filename': Path(filepath).name,
                    'data': f'data:image/png;base64,{img_data}'
                })
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<filename>')
def download(filename):
    """下载单张图片"""
    filepath = Path('output') / filename
    if filepath.exists():
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': '文件不存在'}), 404


@app.route('/upload-image', methods=['POST'])
def upload_image():
    """上传图片（用于手动添加图片到卡片）
    支持 base64 格式或文件上传
    """
    try:
        if 'file' in request.files:
            # 文件上传方式
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': '没有选择文件'}), 400
            
            # 检查文件类型
            allowed_extensions = {'png', 'jpg', 'jpeg', 'webp'}
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
            if ext not in allowed_extensions:
                return jsonify({'error': f'不支持的图片格式，仅支持: {", ".join(allowed_extensions)}'}), 400
            
            # 读取并转为 base64
            img_data = base64.b64encode(file.read()).decode('utf-8')
            mime_type = f'image/{ext}' if ext != 'jpg' else 'image/jpeg'
            
            return jsonify({
                'success': True,
                'image_data': f'data:{mime_type};base64,{img_data}'
            })
        
        elif request.json and 'image_data' in request.json:
            # base64 方式（粘贴/拖拽）
            image_data = request.json['image_data']
            
            # 验证是否为有效的 base64 图片
            if not image_data.startswith('data:image/'):
                return jsonify({'error': '无效的图片数据'}), 400
            
            # 检查是否为 GIF
            if 'image/gif' in image_data:
                return jsonify({'error': '不支持 GIF 格式'}), 400
            
            return jsonify({
                'success': True,
                'image_data': image_data
            })
        
        else:
            return jsonify({'error': '请提供图片文件或 base64 数据'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/validate-image-url', methods=['POST'])
def validate_image_url_endpoint():
    """验证图片 URL 是否可访问"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({'valid': False, 'error': '请提供图片 URL'})
        
        # 检查是否为 GIF
        if url.lower().endswith('.gif'):
            return jsonify({'valid': False, 'error': '不支持 GIF 格式'})
        
        # 导入验证函数
        from main import validate_image_url
        
        is_valid = validate_image_url(url)
        
        return jsonify({
            'valid': is_valid,
            'url': url if is_valid else None,
            'error': None if is_valid else '图片无法访问'
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)})

@app.route('/download-all')
def download_all():
    """下载所有图片（ZIP）"""
    output_dir = Path('output')
    png_files = list(output_dir.glob('slide_*.png'))
    
    if not png_files:
        return jsonify({'error': '没有可下载的图片'}), 404
    
    # 创建 ZIP 文件
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filepath in sorted(png_files):
            zf.write(filepath, filepath.name)
    
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='xiaohongshu_slides.zip'
    )


@app.route('/check-sensitive', methods=['POST'])
def check_sensitive():
    """敏感词检测 API"""
    try:
        data = request.json
        content = data.get('content', '')
        
        if not content:
            return jsonify({
                'success': True,
                'has_sensitive': False,
                'total_count': 0,
                'details': [],
                'summary': {},
                'highlighted_text': ''
            })
        
        # 检测敏感词
        result = detect_sensitive_words(content)
        
        # 生成高亮文本
        highlighted_text = highlight_sensitive_words(content, result)
        
        return jsonify({
            'success': True,
            'has_sensitive': result['has_sensitive'],
            'total_count': result['total_count'],
            'details': result['details'],
            'summary': result['summary'],
            'highlighted_text': highlighted_text
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get-sensitive-categories')
def get_sensitive_categories():
    """获取敏感词分类信息"""
    try:
        categories = get_sensitive_words_by_category()
        return jsonify({
            'success': True,
            'categories': categories
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    Path('output').mkdir(exist_ok=True)
    # 监听 '::' 以同时支持 IPv6 和 IPv4：
    # macOS 上 localhost 优先解析为 ::1，只绑定 127.0.0.1 会导致连接被拒绝。
    app.run(debug=True, use_reloader=False, host='::', port=5001)
