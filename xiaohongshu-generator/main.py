#!/usr/bin/env python3
"""
小红书图文生成工具
读取长文 -> AI 总结为幻灯片 -> 渲染 HTML -> Playwright 截图
支持 Markdown 富文本输入和智能图片分配
"""

import json
import os
import re
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import requests
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from google.generativeai.types import RequestOptions

import ai_providers

# AI 请求超时时间（秒）。没有超时会导致代理不可用时请求永久挂起。
REQUEST_TIMEOUT = ai_providers.REQUEST_TIMEOUT


def _request_options() -> RequestOptions:
    """构造带超时的请求选项，避免网络不通时无限等待"""
    return RequestOptions(timeout=REQUEST_TIMEOUT)


def read_input_file(filepath: str = "input.txt") -> str:
    """读取输入的长文文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def extract_images_from_markdown(content: str) -> tuple[str, list[str]]:
    """
    从 Markdown 内容中提取图片 URL
    返回: (纯文本内容, 图片URL列表)
    """
    # 匹配 Markdown 图片语法: ![alt](url)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    
    images = []
    
    def replace_image(match):
        alt_text = match.group(1)
        url = match.group(2).strip()
        
        # 跳过 GIF 图片
        if url.lower().endswith('.gif'):
            return f'[图片: {alt_text}]' if alt_text else ''
        
        # 只接受网络图片
        if url.startswith(('http://', 'https://')):
            images.append(url)
            return f'[图片: {alt_text}]' if alt_text else ''
        
        return f'[图片: {alt_text}]' if alt_text else ''
    
    # 替换图片标记，提取纯文本
    text_content = re.sub(image_pattern, replace_image, content)
    
    # 清理多余空行
    text_content = re.sub(r'\n{3,}', '\n\n', text_content)
    
    return text_content.strip(), images


def validate_image_url(url: str, timeout: int = 5) -> bool:
    """
    验证图片 URL 是否可访问
    使用 HEAD 请求检查，失败则静默跳过
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            # 检查是否为图片类型
            return 'image' in content_type.lower()
        return False
    except Exception:
        return False


def filter_valid_images(image_urls: list[str]) -> list[str]:
    """
    过滤有效的图片 URL
    - 跳过 GIF
    - 验证 URL 可访问性
    """
    valid_images = []
    
    for url in image_urls:
        # 再次检查 GIF（双重保险）
        if url.lower().endswith('.gif'):
            continue
        
        # 检查支持的格式
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        supported_formats = ('.png', '.jpg', '.jpeg', '.webp')
        
        # 如果 URL 路径有明确的扩展名，检查是否支持
        has_extension = any(path_lower.endswith(ext) for ext in supported_formats + ('.gif',))
        
        if has_extension and not any(path_lower.endswith(ext) for ext in supported_formats):
            continue
        
        # 验证 URL 可访问性
        if validate_image_url(url):
            valid_images.append(url)
    
    return valid_images


import time

def summarize_to_slides(content: str, image_urls: list[str] = None) -> dict:
    """
    调用 Gemini API 将长文总结为幻灯片格式的 JSON，AI 自主决定图片数量
    如果提供了图片 URL 列表，AI 会智能分配图片到对应卡片
    """
    start_time = time.time()
    provider_id = ai_providers.active_provider()
    provider_label = ai_providers.PROVIDERS[provider_id]["label"]
    model_name = ai_providers.get_model(provider_id)
    print(f"⏳ 开始调用 {provider_label} API（模型: {model_name}）...")
    
    char_count = len(content)
    has_images = image_urls and len(image_urls) > 0
    
    # 构建图片分配说明
    image_instruction = ""
    if has_images:
        image_list = "\n".join([f"  {i+1}. {url}" for i, url in enumerate(image_urls)])
        image_instruction = f"""

【图片分配任务】
用户提供了 {len(image_urls)} 张图片，请根据内容相关度智能分配到卡片中：

可用图片列表：
{image_list}

图片分配规则：
1. 每张卡片最多分配 1 张图片
2. 根据图片 URL 和内容的相关性进行匹配
3. 如果图片数量 > 卡片数量：丢弃相关度最低的图片
4. 如果图片数量 < 卡片数量：只为相关度最高的卡片分配图片，其他卡片的 image 设为 null
5. 如果图片数量 = 卡片数量：按相关度一一分配
6. 封面卡片也可以分配图片（cover_image 字段）

输出格式中需要包含 cover_image 和每个 slide 的 image 字段：
- 有图片时填入完整 URL
- 无图片时填入 null
"""
    
    # 构建 JSON 结构说明
    json_structure = """{{
    "cover_title": "封面大标题（简短有力，10字以内）",
    "cover_subtitle": "封面副标题（一句话概括文章主旨）",
    "cover_tags": ["标签1", "标签2", "标签3"],
    "cover_image": null,
    "slides": [
        {{
            "title": "第1张幻灯片标题",
            "content": ["要点1", "要点2", "要点3", "要点4"],
            "image": null
        }}
    ]
}}""" if has_images else """{{
    "cover_title": "封面大标题（简短有力，10字以内）",
    "cover_subtitle": "封面副标题（一句话概括文章主旨）",
    "cover_tags": ["标签1", "标签2", "标签3"],
    "slides": [
        {{
            "title": "第1张幻灯片标题",
            "content": ["要点1", "要点2", "要点3", "要点4"]
        }}
    ]
}}"""

    prompt = f"""你是一个专业的内容编辑，擅长将长文总结为小红书风格的图文内容。

请分析下面的长文，根据内容的信息量、结构和逻辑，自主决定需要多少张内容幻灯片（5-8张），输出严格的 JSON 格式：

{json_structure}
{image_instruction}

图片数量决策原则：
- 分析文章的核心观点数量、信息密度、逻辑结构
- 如果内容简单、观点集中：5-6 张内容页即可
- 如果内容丰富、观点多元：7-8 张内容页更合适
- 确保每张幻灯片信息量充足，不要为了凑数而拆分
- 也不要为了压缩而丢失重要信息
- 最少 5 张内容页（总共 6 张含封面），最多 8 张内容页（总共 9 张含封面）

内容提炼要求：
1. 封面标题要吸引眼球，使用小红书风格的表达（10字以内）
2. 封面标签（cover_tags）要根据文章主题生成3-5个相关标签，每个标签3-6字
3. 每张幻灯片的 title 简洁有力（8字以内）
4. 每张幻灯片的 content 包含 3-5 个要点
5. 每个要点控制在 35 字以内，信息密度要高
6. 内容要有逻辑递进，从引入到总结

标签生成原则：
- 标签要与文章主题高度相关
- 使用小红书常见的标签风格（如：干货分享、实用技巧、新手必看等）
- 标签要简短有力，3-6个字
- 生成3-5个标签

内容提炼原则（重要）：
- 保留所有核心观点、关键数据、重要案例
- 不要丢失文章中的具体数字、百分比、时间节点等关键信息
- 如果文章有多个并列观点，每个观点都要体现
- 专有名词、产品名称、人名等必须保留
- 每张幻灯片信息量要充足，避免过度简化
- 优先保留"干货"内容，而非空泛的总结

文章字数：{char_count} 字
文章内容：
{content}

只输出 JSON，不要其他内容。"""

    try:
        raw_text = ai_providers.generate_json(prompt, temperature=0.7)
    except ai_providers.AIProviderError as e:
        print(f"❌ {provider_label} API 调用出错 [{e.code}]: {e.detail or e}")
        raise
    except Exception as e:
        print(f"❌ {provider_label} API 调用出错: {e}")
        raise RuntimeError(f"AI 接口调用失败：{type(e).__name__}: {str(e)[:300]}") from e
    
    elapsed_time = time.time() - start_time
    print(f"✅ {provider_label} API 调用完成，耗时: {elapsed_time:.2f}秒")

    # 尝试解析 JSON
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"原始响应: {raw_text}")
        # 返回一个包含错误信息的默认结构，避免程序崩溃
        return {
            "cover_title": "生成失败",
            "cover_subtitle": "请重试或检查日志",
            "cover_tags": ["错误"],
            "cover_image": None,
            "slides": [
                {
                    "title": "解析错误",
                    "content": ["AI 返回的数据格式不正确", "请查看后台日志"],
                    "image": None
                }
            ]
        }
    except Exception as e:
        print(f"❌ 解析响应出错: {e}")
        raise e
    
    # 确保返回的数据结构包含图片字段（即使 AI 没有返回）
    if 'cover_image' not in result:
        result['cover_image'] = None
    
    # 验证和修复每个 slide 的数据完整性
    for i, slide in enumerate(result.get('slides', []), 1):
        # 确保有 image 字段
        if 'image' not in slide:
            slide['image'] = None
        
        # 确保 title 字段存在且不为空
        if 'title' not in slide or not slide['title'] or not slide['title'].strip():
            slide['title'] = f"第 {i} 部分"  # 提供默认标题
            print(f"⚠️  警告: 第 {i} 张幻灯片缺少标题，已自动补充默认标题")
        
        # 确保 content 字段存在且为列表
        if 'content' not in slide or not isinstance(slide['content'], list):
            slide['content'] = []
            print(f"⚠️  警告: 第 {i} 张幻灯片缺少内容")
    
    return result


def render_html(slides_data: dict, style: str = "xiaohongshu") -> str:
    """使用 Jinja2 渲染 HTML 模板"""
    # 根据风格选择模板
    template_map = {
        "xiaohongshu": "template.html",
        "apple": "template_apple.html",
        "neobrutalist": "template_neobrutalist.html",
        "capsule": "template_capsule.html",
        "tech": "template_tech.html",
        "notion": "template_notion.html",
        "memphis": "template_memphis.html",
        "chinese": "template_chinese.html",
        "polaroid": "template_polaroid.html",
        "streaming": "template_streaming.html",
        "journal": "template_journal.html",
        "magazine": "template_magazine.html",
        "ins": "template_ins.html",
    }
    
    template_file = template_map.get(style, "template.html")
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template(template_file)
    return template.render(**slides_data)


async def capture_slides(html_content: str, output_dir: str = "output") -> list[str]:
    """使用 Playwright 截图每张卡片"""
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 清理旧的图片文件，避免残留
    for old_file in output_path.glob("slide_*.png"):
        old_file.unlink()
        print(f"🗑️ 已清理旧文件: {old_file.name}")

    # 创建临时 HTML 文件
    temp_html = Path("_temp_render.html")
    temp_html.write_text(html_content, encoding="utf-8")

    output_files = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1600, "height": 2000},
            device_scale_factor=2,  # 高清截图
        )

        # 加载渲染后的 HTML
        await page.goto(f"file://{temp_html.absolute()}")
        await page.wait_for_load_state("networkidle")

        # 获取所有卡片元素并截图
        card_index = 1
        while True:
            card = page.locator(f"#card-{card_index}")
            if await card.count() == 0:
                break

            file_path = f"{output_dir}/slide_{card_index}.png"
            await card.screenshot(path=file_path)
            output_files.append(file_path)
            print(f"✅ 已生成: {file_path}")
            card_index += 1

        await browser.close()

    # 清理临时文件
    temp_html.unlink()

    return output_files


async def main():
    """主流程"""
    print("📖 读取输入文件...")
    content = read_input_file()
    char_count = len(content)
    print(f"   文章长度: {char_count} 字")

    print("\n🤖 调用 AI 分析内容并生成幻灯片...")
    print("   AI 将根据内容结构自主决定图片数量（6-9 张）")
    slides_data = summarize_to_slides(content)
    print(f"   封面标题: {slides_data['cover_title']}")
    print(f"   AI 决定生成: {len(slides_data['slides']) + 1} 张图片（1 封面 + {len(slides_data['slides'])} 内容页）")

    # 保存 JSON 结果
    with open("output/slides_data.json", "w", encoding="utf-8") as f:
        json.dump(slides_data, f, ensure_ascii=False, indent=2)
    print("\n💾 JSON 数据已保存到 output/slides_data.json")

    print("\n🎨 渲染 HTML 模板...")
    html_content = render_html(slides_data)

    print("\n📸 使用 Playwright 截图...")
    output_files = await capture_slides(html_content)

    print(f"\n🎉 完成！共生成 {len(output_files)} 张图片")
    print("   输出目录: output/")


if __name__ == "__main__":
    # 确保 output 目录存在
    Path("output").mkdir(exist_ok=True)
    asyncio.run(main())
