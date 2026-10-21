#!/usr/bin/env python3
"""Real browser flows against Flask with an offline model transport double."""
import asyncio
import base64
from contextlib import closing
import copy
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from playwright.async_api import async_playwright
from werkzeug.serving import make_server, WSGIRequestHandler
import app as service
from main import ROOT
from scripts.generate_samples import SAMPLE


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs): pass
    def log_error(self, *args, **kwargs): pass


discovery_started = threading.Event()
discovery_finished = threading.Event()
format_attempts = []


def offline_model(url, **kwargs):
    key = kwargs['headers'].get('Authorization', '')
    discovery = kwargs.get('body') is None
    if 'balance-key' in key and not discovery:
        return 402, 'application/json', b'{"error":{"message":"do-not-show-private-balance"}}'
    if 'fail-key' in key or ('fail-generation-key' in key and not discovery):
        return 401, 'application/json', b'{"upstream_secret":"do-not-show"}'
    if discovery:
        if 'delay-list-key' in key:
            discovery_started.set(); time.sleep(1.2); discovery_finished.set()
        if 'qianfan.baidubce.com' in url:
            rows = [{'id':'ernie-5.1','owned_by':'Baidu','type':'chat','endpoints':['/v2/chat/completions']},
                    {'id':'ernie-5.1-audio','owned_by':'Baidu','type':'audio','endpoints':['/v2/chat/completions']},
                    {'id':'deepseek-v4','owned_by':'DeepSeek','type':'chat','endpoints':['/v2/chat/completions']}]
        elif 'tokenhub.tencentmaas.com' in url:
            rows = [{'id':'hy3','status':'online'}, {'id':'hy4','status':'offline'},
                    {'id':'hy-image-v3','status':'online'}]
        elif 'many-models-key' in key:
            rows = [{'id':f'deepseek-test-{index:02}'} for index in range(1, 31)]
        else:
            model = 'kimi-k3' if 'moonshot.cn' in url else 'deepseek-flash'
            rows = [{'id':model},{'id':model+'-audio'}]
        return 200, 'application/json', json.dumps({'data':rows}).encode()
    if 'delay-key' in key: time.sleep(1.2)
    payload = json.loads(kwargs['body'])
    prompt = payload['messages'][0]['content']
    if prompt.startswith('以不同表述'):
        data = json.loads(prompt.split('\n', 1)[1])
        data['title' if 'title' in data else 'cover_title'] = '重新整理的表达'
    else:
        data = copy.deepcopy(SAMPLE)
        data['slides'].append({'title': '持续创作', 'content': ['把真实的观察记下来。', '留出复盘与思考的时间。'], 'image': None})
    if not prompt.startswith('以不同表述'):
        if '【配图20：主题20示意图】' in prompt:
            format_attempts.append('card_fields')
            data.pop('cover_tags'); data['cover_subtitle'] = None
            data['cover_image'] = '20'
            data['slides'] = [{'title': f'内容主题{i}', 'content':['对应的核心观点。'], 'image':str(i*2)} for i in range(1,8)]
            if '上次输出' not in prompt:
                data['cover_title'] = '这是一段超过二十四个字符的模型封面标题需要模型主动提炼'
                data['slides'].append({'title':'超量页','content':['应合并至七个内容页。']})
        elif '【配图1：示例配图】' in prompt:
            data['cover_image'] = 1
    text = json.dumps(data, ensure_ascii=False)
    if '格式恢复测试' in prompt or '格式持续失败测试' in prompt:
        format_attempts.append('json')
        if '上次输出' not in prompt or '格式持续失败测试' in prompt:
            text = '这是未遵守 JSON 要求的离线模型响应。'
    elif '【配图20：主题20示意图】' in prompt:
        text = '```JSON\n' + text + '\n```'
    response = ({'content': [{'type': 'thinking', 'thinking': 'test reasoning'}, {'type': 'text', 'text': text}], 'stop_reason': 'end_turn'} if '/anthropic/' in url
                else {'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})
    return 200, 'application/json', json.dumps(response).encode()


image_requests = []


def offline_image(url, **kwargs):
    image_requests.append(url)
    if url.endswith('/blocked.png'):
        return 403, 'text/html', b'Forbidden'
    output = io.BytesIO()
    Image.new('RGB', (600, 300), '#ba5745').save(output, 'PNG')
    return 200, 'image/png', output.getvalue()


async def verify(url, database, temporary):
    artifacts = ROOT / 'output/playwright'; artifacts.mkdir(parents=True, exist_ok=True)
    checks, errors, accessibility = [], [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1000})
        page = await context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
        async def shot(name):
            await page.evaluate('document.fonts.ready')
            await page.locator('.result-card').evaluate_all('(els)=>Promise.all(els.flatMap(el=>el.getAnimations().map(animation=>animation.finished.catch(()=>{}))))')
            await page.locator('.result-card img').evaluate_all('(els)=>Promise.all(els.map(img=>img.decode()))')
            audit = await page.evaluate(r"""() => {
              const rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number);
              const luminance=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
              const failures=[];let minimum=100,checked=0;
              for(const el of document.querySelectorAll('body *')) {
                if(!el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||el.closest('svg,button:disabled'))continue;
                if(![...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&!el.matches('input,textarea'))continue;
                const layers=[];for(let p=el;p;p=p.parentElement)layers.unshift(rgb(getComputedStyle(p).backgroundColor));
                let bg=[255,255,255];for(const c of layers){const a=c[3]??1;bg=bg.map((v,i)=>v*(1-a)+c[i]*a)}
                const color=rgb(getComputedStyle(el).color),a=color[3]??1;
                const fg=bg.map((v,i)=>v*(1-a)+color[i]*a),x=luminance(fg),y=luminance(bg);
                const ratio=(Math.max(x,y)+.05)/(Math.min(x,y)+.05);minimum=Math.min(minimum,ratio);checked++;
                if(ratio<4.5)failures.push({element:el.tagName,id:el.id,ratio,text:el.textContent.slice(0,30)});
              }
              return {minimum,checked,failures};
            }""")
            assert not audit['failures'], (name, audit['failures'])
            accessibility.append({'state':name,'minimum_text_contrast':round(audit['minimum'],2),'text_elements':audit['checked']})
            await page.screenshot(path=artifacts / f'{name}.png', full_page=True)
        async def no_overflow():
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.url
        async def desktop_fits():
            viewport = await page.evaluate('''() => ({width:innerWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight,overflow:[...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().bottom>innerHeight+1).map(el=>({tag:el.tagName,id:el.id,class:el.className,bottom:Math.round(el.getBoundingClientRect().bottom)})).slice(0,16)})''')
            assert viewport['scrollHeight'] <= viewport['height'] + 1, viewport
            for selector in ('.workspace-brand', '#content', '#generate', '#style-gallery', '#card-stage', '.edit-card', '.result-card'):
                for element in await page.locator(selector).all():
                    if not await element.is_visible():
                        continue
                    box = await element.bounding_box()
                    height = await page.evaluate('innerHeight')
                    assert box['y'] >= -1 and box['y'] + box['height'] <= height + 1, (selector, box, height)
            height = await page.evaluate('innerHeight')
            assert (await page.locator('#content').bounding_box())['height'] >= height * .5
            gallery_height = (await page.locator('#style-gallery').bounding_box())['height']
            assert gallery_height <= height * .28, (await page.evaluate('innerWidth'), height, gallery_height)
            footer = await page.locator('.workspace-footer').bounding_box()
            workspace = await page.locator('.workspace').bounding_box()
            desk = await page.locator('.desk').bounding_box()
            assert abs(footer['x'] + footer['width'] - workspace['x'] - workspace['width']) < 2
            assert footer['y'] >= desk['y'] + desk['height'] - 1
            assert footer['y'] + footer['height'] <= workspace['y'] + workspace['height'] + 1
            if await page.locator('#style-gallery').get_attribute('open') is not None:
                assert await page.locator('#style-gallery').evaluate('(el)=>[...el.querySelectorAll(".style-option")].every(item=>{const r=item.getBoundingClientRect();return r.top>=0 && r.bottom<=el.getBoundingClientRect().bottom+1 && r.right<=innerWidth})')
        for width in (375, 768, 1024, 1440):
            await page.set_viewport_size({'width': width, 'height': 900})
            await page.goto(url); await no_overflow(); await shot(f'home-{width}')
            assert await page.locator('.gallery-item').count() == 12
            await page.goto(url + '/app?style=chinese'); await no_overflow(); await shot(f'app-{width}')
            assert await page.locator('#empty-state').is_visible()
            assert await page.locator('#empty-state').evaluate('(el)=>el.parentElement.id === "card-stage" && el.textContent.includes("先把内容说好，再让设计发生。")')
            assert await page.get_by_role('button', name='生成图卡文案').count() == 1
            assert await page.get_by_label('① 请输入你的内容', exact=True).count() == 1
            assert await page.locator('.workspace-credit').count() == 0
            assert '来自 AI 编程瓜哥' not in await page.locator('body').inner_text()
            assert await page.locator('.workspace-key-note').count() == 0
            assert await page.locator('.workspace-footer').inner_text() == '本站不保存任何信息，刷新后清空。'
            assert await page.locator('#content-help').evaluate('(el)=>el.getBoundingClientRect().bottom<=document.querySelector("#content").getBoundingClientRect().top')
            content_font = await page.locator('#content').evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)')
            assert content_font == 16 if width <= 600 else 11 <= content_font <= 12
            assert await page.locator('#style-select').input_value() == 'chinese'
            assert await page.locator('.style-option input:checked').input_value() == 'chinese'
            assert await page.locator('.style-option').count() == 37
            assert await page.locator('.style-option input[value="ppt-y2k-chrome"]').count() == 0
            assert await page.locator('.style-icon').first.get_attribute('viewBox') == '0 0 64 48'
            assert await page.locator('.style-icon').first.evaluate('(el)=>Math.abs(el.getBoundingClientRect().width / el.getBoundingClientRect().height - 4/3) < .02')
            if width >= 1024:
                await desktop_fits()
                box = await page.locator('#generate').bounding_box()
                assert box['y'] + box['height'] <= 900, (width, box)
                assert (await page.locator('#content').bounding_box())['width'] == (320 if width <= 1150 else 370)
            await page.locator('#model-config summary').focus()
            await page.keyboard.press('Enter')
            assert await page.locator('#model-config').get_attribute('open') is not None
            assert await page.locator('#model-config summary').evaluate('(el)=>parseFloat(getComputedStyle(el).outlineWidth)>=2')
            await page.keyboard.press('Enter')
            await page.locator('#model-config summary').click()
            for selector in ('#generate', '#content'):
                box = await page.locator(selector).first.bounding_box(); assert box['height'] >= 44 and box['width'] >= 44
            box = await page.locator('.style-option').first.bounding_box()
            assert box['height'] >= (44 if width <= 600 else 36) and box['width'] >= 44
            control_height = 44 if width <= 600 else 36
            for selector in ('#provider', '.key-field', '#refresh-models', '#model', '#save-config'):
                box = await page.locator(selector).bounding_box(); assert box['height'] >= control_height
            await page.locator('#api-key').fill('sk-' + 'x' * 240)
            await page.locator('#toggle-key').click()
            assert await page.locator('#api-key').get_attribute('type') == 'text'
            assert await page.locator('.key-field').evaluate('(el)=>el.querySelector("input").getBoundingClientRect().right <= el.querySelector("button").getBoundingClientRect().left + 1')
            await page.locator('#toggle-key').click()
            assert await page.locator('#api-key').input_value() == 'sk-' + 'x' * 240
            await no_overflow(); await shot(f'config-{width}')
            checks.append(f'{width}px: no overflow; compact config controls >= {control_height}px; long Key and toggle occupy separate areas')
        async def configure(provider='deepseek', key='test-only-key'):
            if await page.locator('#model-config').get_attribute('open') is None:
                await page.locator('#model-config summary').click()
            if await page.locator('#provider').input_value() != provider:
                await page.locator('#provider').select_option(provider)
            await page.locator('#api-key').fill(key)
            await page.locator('#refresh-models').click()
            await page.locator('#model:not(:disabled)').wait_for()
            options = await page.locator('#model option').evaluate_all('(els)=>els.map(el=>el.value).filter(Boolean)')
            assert await page.locator('#model').evaluate('(el)=>el.size') == 1
            await page.locator('#model').click()
            assert await page.locator('#model').evaluate('(el)=>el.size') == len(options) + 1
            assert await page.locator('#model').evaluate('(el)=>el.clientHeight >= el.scrollHeight - 1')
            await page.locator('#model option').nth(1).click()
            assert await page.locator('#model').input_value() == options[0]
            assert options[0] in await page.locator('#model-selection').inner_text()
            assert await page.locator('#model').evaluate('(el)=>el.size') == 1
            await page.locator('#model').click()
            await page.locator('#model option').nth(1).click()
            assert await page.locator('#model').evaluate('(el)=>el.size') == 1
            return options
        await page.locator('#api-key').fill('')
        await page.locator('#save-config').click()
        assert await page.locator('#key-error').inner_text()
        assert await page.locator('#model-error').inner_text()
        assert await page.locator('#model-config').get_attribute('open') is not None
        long_key = 'sk-' + 'x' * 240
        configured_models = await configure(key=long_key)
        await page.locator('#toggle-key').click()
        await shot('config-long-key-visible')
        await page.locator('#save-config').click()
        assert await page.locator('#model-config').get_attribute('open') is None
        assert await page.locator('#model-config summary').evaluate('(el)=>el===document.activeElement')
        assert await page.locator('#api-key').input_value() == long_key
        assert await page.locator('#api-key').get_attribute('type') == 'password'
        assert await page.locator('#toggle-key').get_attribute('aria-pressed') == 'false'
        assert await page.locator('#model').input_value() == configured_models[0]
        assert await page.evaluate('localStorage.length + sessionStorage.length') == 0
        await page.locator('#model-config summary').click()
        await shot('config-saved-reopened')
        checks.append('save config: rejects missing fields; preserves current-page values; masks Key, closes panel and restores focus; no browser storage')
        service._rates.clear()
        assert await page.locator('#provider option').count() == 8
        assert await page.locator('#protocol,#base-url').count() == 0
        live_providers = ('deepseek', 'kimi', 'qianfan', 'hunyuan')
        for provider in ('deepseek', 'minimax', 'kimi', 'zhipu', 'doubao', 'qwen', 'qianfan', 'hunyuan'):
            options = await configure(provider)
            assert options
            assert await page.locator('#model-status').inner_text() == ''
            await shot('provider-' + provider)
        assert len(await configure('deepseek', 'many-models-key')) == 30
        await page.locator('#model').press('Enter')
        assert await page.locator('#model').evaluate('(el)=>el.size') == 31
        await shot('models-all-visible')
        await page.locator('#model').press('ArrowDown')
        await page.locator('#model').press('Enter')
        assert await page.locator('#model').input_value() == 'deepseek-test-02'
        assert await page.locator('#model').evaluate('(el)=>el.size') == 1
        await page.locator('#model').press('Enter')
        await page.locator('#model').press('Escape')
        assert await page.locator('#model').evaluate('(el)=>el.size') == 1
        checks.append('model menu: click opens all options; choice and repeated choice collapse; keyboard arrows/Enter select; Escape collapses')
        with closing(sqlite3.connect(database)) as db:
            assert db.execute("SELECT COUNT(*) FROM counts WHERE event LIKE 'generation_%'").fetchone()[0] == 0
        await page.locator('#provider').select_option('deepseek')
        assert await page.locator('#api-key').input_value() == ''
        assert await page.locator('#model').is_disabled()
        await page.locator('#api-key').fill('fail-key'); await page.locator('#refresh-models').click()
        await page.locator('#model-error').filter(has_text='模型鉴权失败').wait_for()
        assert await page.locator('#api-key').input_value() == 'fail-key'
        assert await page.locator('#model').is_disabled()
        await shot('models-error')
        await page.locator('#api-key').fill('delay-list-key'); await page.locator('#refresh-models').click()
        assert await asyncio.to_thread(discovery_started.wait, 3)
        assert await page.locator('#save-config').is_disabled()
        await shot('models-loading')
        await page.locator('#provider').select_option('kimi')
        assert await page.locator('#api-key').input_value() == ''
        await configure('kimi', 'new-kimi-key')
        assert await asyncio.to_thread(discovery_finished.wait, 3)
        assert await page.locator('#model').input_value() == 'kimi-k3'
        assert await page.locator('#api-key').input_value() == 'new-kimi-key'
        assert await page.locator('#model option').count() == 2
        await page.locator('#api-key').fill('changed-key')
        assert await page.locator('#model').is_disabled()
        service._rates.clear()
        await configure('minimax')
        await page.get_by_role('button', name='填入示例').click()
        await page.locator('#generate').click(); await page.locator('#status').filter(has_text='文案已整理').wait_for()
        assert await page.locator('.edit-card').count() == 3
        checks.append('eight domestic providers; no protocol/URL field; four live model lists and four dated catalogs; no inference on refresh; discovery errors; provider clears Key; Key edits clear models; late discovery cannot overwrite another provider; MiniMax Anthropic generation')
        service._rates.clear()
        await page.goto(url)
        await page.get_by_role('button', name='查看全部 37 款样式').click()
        assert await page.locator('.gallery-item').count() == 37
        await page.get_by_role('button', name='放大苹果极简样例', exact=True).click()
        assert await page.locator('#image-dialog').is_visible()
        await shot('sample-dialog'); await page.keyboard.press('Escape')
        assert not await page.locator('#image-dialog').is_visible()
        assert await page.get_by_role('button', name='放大苹果极简样例', exact=True).evaluate('(el)=>el===document.activeElement')
        await page.locator('.gallery-item').nth(1).get_by_role('link', name='使用此样式').click()
        assert await page.locator('#style-select').input_value() == 'apple'
        await page.get_by_role('button', name='生成图卡文案').click()
        assert await page.locator('#key-error').inner_text(); assert await page.locator('#content-error').inner_text()
        await shot('validation-error')
        await configure()
        article = '用于回归验证的自有图卡内容。' * 8
        format_attempts.clear()
        with closing(sqlite3.connect(database)) as db:
            before_repair = dict(db.execute('SELECT event,SUM(count) FROM counts GROUP BY event'))
        await page.locator('#content').fill(article + '格式恢复测试')
        await page.locator('#generate').click()
        await page.locator('#status').filter(has_text='文案已整理').wait_for()
        assert not await page.locator('#empty-state').is_visible()
        assert format_attempts == ['json', 'json']
        with closing(sqlite3.connect(database)) as db:
            after_repair = dict(db.execute('SELECT event,SUM(count) FROM counts GROUP BY event'))
        assert after_repair['generation_success'] == before_repair.get('generation_success', 0) + 1
        assert after_repair.get('generation_failure', 0) == before_repair.get('generation_failure', 0)
        await shot('format-recovered')
        await page.locator('#content').fill(article + '格式持续失败测试')
        await page.locator('#generate').click()
        await page.locator('#status').filter(has_text='模型未返回有效 JSON').wait_for()
        assert format_attempts == ['json'] * 4
        assert await page.locator('#content').input_value() == article + '格式持续失败测试'
        assert await page.locator('.edit-card').count() == 3
        await shot('format-error')
        service._rates.clear()
        bad_image = article + '\n![示例配图](https://images.example.com/blocked.png)'
        await page.locator('#content').fill(bad_image)
        await page.locator('#generate').click()
        await page.locator('#status').filter(has_text='文案已整理').wait_for()
        await page.locator('#status').filter(has_text='已跳过，可在编辑区补图').wait_for()
        assert await page.locator('#content-error').inner_text() == ''
        assert await page.locator('#content').input_value() == bad_image
        assert await page.locator('#model').input_value() == 'deepseek-flash'
        await shot('image-skipped')
        many_images = '\n'.join(f'第{i}个主题的正文说明。![主题{i}示意图](https://images.example.com/{i}.png)' for i in range(1,21))
        await page.locator('#content').fill(many_images)
        image_requests.clear()
        await page.locator('#generate').click()
        await page.locator('#status').filter(has_text='20 张候选配图中采用 8 张').wait_for()
        assert await page.locator('.edit-card').count() == 8
        assert await page.locator('#render').inner_text() == '⑤ 生成图卡'
        render_box = await page.locator('#render').bounding_box()
        stage_box = await page.locator('#card-stage').bounding_box()
        output_box = await page.locator('.output-column').bounding_box()
        assert render_box['y'] >= stage_box['y'] + stage_box['height'] - 1
        assert abs(render_box['x'] + render_box['width'] - (output_box['x'] + output_box['width'])) < 2
        assert len(image_requests) == 8
        assert image_requests[0].endswith('/20.png') and not any(url.endswith('/1.png') for url in image_requests)
        assert format_attempts.count('card_fields') == 2
        dense = page.locator('.edit-card').nth(1)
        await dense.get_by_role('textbox').first.fill('在日常创作里发现并记录那些容易被忽略的真实细节'[:24])
        long_point = ('把每天看到的细节和突然冒出的想法记下来，不急着判断价值，用具体故事支撑自己的观点。' * 2)[:50]
        await dense.locator('.point-row textarea').first.fill(long_point)
        for _ in range(4):
            await dense.get_by_role('button', name='+ 添加要点').click()
            await dense.locator('.point-row textarea').last.fill(long_point)
        assert await dense.locator('.point-row').count() == 5
        assert await dense.locator('.card-copy').evaluate('(el)=>el.scrollHeight > el.clientHeight')
        await dense.locator('.card-copy').evaluate('(el)=>el.scrollTop=0')
        await dense.screenshot(path=artifacts / 'dense-draft-card.png')
        assert await page.locator('#style-gallery').get_attribute('open') is not None
        assert await page.locator('#editor').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == 4
        boxes = await page.locator('.edit-card').evaluate_all('(els)=>els.map(el=>({x:el.offsetLeft,y:el.offsetTop}))')
        assert len({box['y'] for box in boxes}) == 2
        for width, height, columns in ((375, 900, 1), (640, 900, 2), (768, 900, 2), (1024, 768, 4), (1280, 720, 4), (1440, 900, 4), (1920, 1080, 4)):
            await page.set_viewport_size({'width':width, 'height':height})
            assert await page.locator('#editor').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == columns
            if width >= 640:
                assert await page.locator('.desk').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == 2
            if width >= 1000:
                await desktop_fits()
            await no_overflow(); await shot(f'eight-drafts-{width}')
            if width == 375:
                await page.locator('.edit-card').first.screenshot(path=artifacts / 'mobile-draft-card.png')
        await page.set_viewport_size({'width':768, 'height':600})
        assert await page.locator('.desk').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == 2
        assert await page.locator('#editor').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == 2
        input_box = await page.locator('.input-column').bounding_box()
        assert input_box['height'] <= 491
        await no_overflow()
        await page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
        input_box = await page.locator('.input-column').bounding_box()
        assert input_box['y'] >= 11 and input_box['y'] + input_box['height'] <= 601
        footer_box = await page.locator('.workspace-footer').bounding_box()
        assert footer_box['y'] + footer_box['height'] <= 601
        await shot('eight-drafts-768-low-height')
        await page.set_viewport_size({'width':1440, 'height':900}); await page.evaluate('window.scrollTo(0,0)')
        checks.append('desktop live resize from 640px through 1920px keeps the two-column desk; card columns adapt to width; low-height windows scroll vertically without horizontal overflow')
        for template in ('ppt-gruvbox-dark', 'ppt-rose-pine', 'ppt-glassmorphism'):
            option = page.locator(f'label.style-option:has(input[value="{template}"])')
            await option.hover()
            preview = option.locator('.style-preview')
            await preview.wait_for(state='visible')
            await preview.locator('img').evaluate('(img)=>img.decode()')
            box = await preview.bounding_box()
            assert box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= 1440 and box['y'] + box['height'] <= 900
        await shot('compact-style-hover')
        await page.mouse.move(0, 0)
        await preview.wait_for(state='hidden')
        await shot('many-images-eight-cards')
        await page.locator('#card-stage').screenshot(path=artifacts / 'eight-draft-grid.png')
        gallery_y = await page.locator('#style-gallery').evaluate('(el)=>el.getBoundingClientRect().top + scrollY')
        await page.locator('#render').click()
        await page.locator('#card-stage.is-rendering[aria-busy=true]').wait_for()
        await shot('cards-magic-loading')
        await page.get_by_role('status').filter(has_text='图卡已就绪').wait_for(timeout=60000)
        assert await page.locator('.result-card').count() == 8
        assert await page.locator('#render').inner_text() == '⑤ 重新生成图卡'
        assert not await page.locator('#editor').is_visible()
        assert await page.locator('#card-stage').get_attribute('aria-busy') == 'false'
        assert await page.locator('#style-gallery').get_attribute('open') is not None
        assert await page.locator('#style-gallery').evaluate('(el)=>el.getBoundingClientRect().top + scrollY') == gallery_y
        await shot('eight-cards-download')
        await desktop_fits()
        for width, height in ((1024,768), (1280,720), (1920,1080)):
            await page.set_viewport_size({'width':width, 'height':height})
            await desktop_fits(); await no_overflow(); await shot(f'eight-results-{width}')
        await page.set_viewport_size({'width':1440, 'height':900})
        await page.locator('#card-stage').screenshot(path=artifacts / 'eight-rendered-grid.png')
        async with page.expect_download() as eight_download_info:
            await page.locator('#download-all').click()
        eight_download = await eight_download_info.value
        eight_archive = Path(temporary) / 'eight-cards.zip'
        await eight_download.save_as(eight_archive)
        with zipfile.ZipFile(eight_archive) as archive:
            assert len(archive.namelist()) == 8
            for name in archive.namelist():
                assert Image.open(io.BytesIO(archive.read(name))).size == (1242,1660)
        checks.append('desktop viewport 1024x768/1280x720/1440x900/1920x1080: no page scroll, tall input with unchanged sidebar width, compact gallery, all eight drafts and results visible; mobile responsive; JSON repair and eight PNG ZIP retained')
        service._rates.clear()
        await page.get_by_role('button', name='填入示例').click()
        await page.get_by_role('button', name='生成图卡文案').click()
        await page.locator('#status').filter(has_text='文案已整理').wait_for()
        assert await page.locator('.edit-card').count() == 3
        assert not await page.locator('#model-config').get_attribute('open')
        assert await page.locator('#style-gallery').get_attribute('open') is not None
        await page.locator('#style-gallery summary').click()
        await shot('editor-1440')
        card = page.locator('.edit-card').nth(1)
        await card.get_by_role('button', name='删除要点 2', exact=True).click()
        await card.get_by_role('button', name='+ 添加要点').click()
        await card.get_by_role('textbox').last.fill('删除再添加后的独立要点。')
        assert await card.locator('.point-row').count() == 3
        texts = await card.locator('.point-row textarea').evaluate_all('(els)=>els.map(el=>el.value)')
        assert texts[-1] == '删除再添加后的独立要点。'
        await card.get_by_role('button', name='重新生成此页').click()
        await page.get_by_role('status').filter(has_text='这一页已更新').wait_for()
        assert await page.locator('#style-gallery').get_attribute('open') is None
        assert await card.get_by_role('textbox').first.input_value() == '重新整理的表达'
        photo = Path(temporary) / 'test-photo.png'; Image.new('RGB', (600, 300), '#b4654a').save(photo)
        await card.locator('.image-editor summary').click()
        await card.locator('input[type=file]').set_input_files(photo)
        await page.get_by_role('status').filter(has_text='配图已验证').wait_for()
        assert await card.locator('.image-editor img').count() == 1
        await page.locator('#render').click(); await page.get_by_role('status').filter(has_text='图卡已就绪').wait_for(timeout=60000)
        assert await page.locator('.result-card').count() == 3
        assert await page.locator('#style-gallery').get_attribute('open') is None
        await shot('download-ready-1440')
        async with page.expect_download() as download_info:
            await page.locator('.result-card a').first.click()
        download = await download_info.value
        single = Path(temporary) / 'single.png'; await download.save_as(single)
        assert Image.open(single).size == (1242, 1660)
        async with page.expect_download() as download_info:
            await page.locator('#download-all').click()
        download = await download_info.value
        archive = Path(temporary) / 'cards.zip'; await download.save_as(archive)
        with zipfile.ZipFile(archive) as zipped:
            assert len(zipped.namelist()) == 3
            assert zipped.read('card-01.png') == single.read_bytes()
        await page.locator('#style-gallery summary').click()
        await page.locator('label.style-option:has(input[value="memphis"])').click()
        await page.get_by_role('status').filter(has_text='图卡已就绪').wait_for(timeout=60000)
        assert await page.locator('.result-card').count() == 3
        await page.locator('#edit-cards').click()
        await page.locator('.edit-card').first.get_by_role('textbox').first.fill('保留这次编辑')
        assert not await page.locator('#results-section').is_visible()
        await page.locator('#model-config summary').click()
        service._rates.clear()
        await configure(key='fail-generation-key')
        await page.locator('#generate').click()
        await page.get_by_role('status').filter(has_text='模型鉴权失败').wait_for()
        assert await page.locator('.edit-card').first.get_by_role('textbox').first.input_value() == '保留这次编辑'
        assert 'do-not-show' not in await page.locator('body').inner_text()
        await shot('upstream-error')
        await configure(key='balance-key')
        await page.locator('#generate').click()
        await page.locator('#status[data-kind=error]').filter(has_text='余额不足').wait_for()
        assert 'do-not-show' not in await page.locator('body').inner_text()
        assert await page.locator('.edit-card').first.get_by_role('textbox').first.input_value() == '保留这次编辑'
        await shot('balance-error')
        await configure(key='delay-key')
        await page.locator('#generate').click()
        await page.locator('#status[data-kind=loading]').wait_for()
        assert await page.locator('#status').inner_text() == '正在整理文案，通常需要几秒。'
        await shot('loading')
        await page.locator('.edit-card').first.get_by_role('textbox').first.fill('处理期间的新编辑')
        await page.get_by_role('status').filter(has_text='处理期间内容已变化').wait_for()
        assert await page.locator('.edit-card').first.get_by_role('textbox').first.input_value() == '处理期间的新编辑'
        # Reset only the isolated test server's in-memory budget for additional scenarios.
        service._rates.clear()
        await page.locator('#generate').click(); await page.locator('#cancel-task').click()
        await page.get_by_role('status').filter(has_text='操作已取消').wait_for()
        assert await page.locator('.edit-card').first.get_by_role('textbox').first.input_value() == '处理期间的新编辑'
        for width in (375, 768, 1024):
            await page.set_viewport_size({'width': width, 'height': 900}); await no_overflow(); await shot(f'editor-{width}')
        await page.emulate_media(reduced_motion='reduce')
        assert await page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == 'auto'
        async def failed_render(route):
            await route.fulfill(status=502, json={'error':'测试渲染失败，请重试。'})
        await page.route('**/render', failed_render)
        await page.locator('#render').click()
        await page.locator('#status[data-kind=error]').filter(has_text='测试渲染失败').wait_for()
        assert await page.locator('#editor').is_visible()
        assert await page.locator('#card-stage').get_attribute('aria-busy') == 'false'
        assert await page.locator('#card-stage.is-rendering').count() == 0
        await page.unroute('**/render', failed_render)
        render_route_done = asyncio.Event()
        async def delayed_render(route):
            try:
                await asyncio.sleep(.5)
                await route.abort()
            finally:
                render_route_done.set()
        await page.route('**/render', delayed_render)
        await page.locator('#render').click()
        await page.locator('#card-stage.is-rendering').wait_for()
        assert await page.locator('.card-magic').evaluate('(el)=>getComputedStyle(el).display') == 'none'
        await page.locator('#cancel-task').click()
        await page.locator('#status').filter(has_text='操作已取消').wait_for()
        assert await page.locator('#card-stage.is-rendering').count() == 0
        assert await page.locator('#editor').is_visible()
        await asyncio.wait_for(render_route_done.wait(), 3)
        await page.unroute('**/render', delayed_render)
        checks.append('eight PNGs and ZIP; editing/results switch; style rerender; render failure and cancellation preserve drafts and clear animation; reduced motion hides magic; upload, regeneration, stale-response protection and privacy retained')
        with closing(sqlite3.connect(database)) as db:
            before = dict(db.execute('SELECT event,SUM(count) FROM counts GROUP BY event'))
        await page.reload(); assert await page.locator('#api-key').input_value() == ''; assert await page.locator('#content').input_value() == ''
        assert await page.locator('#model').is_disabled()
        assert await page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
        with closing(sqlite3.connect(database)) as db:
            after = dict(db.execute('SELECT event,SUM(count) FROM counts GROUP BY event'))
            columns = [r[1] for r in db.execute('PRAGMA table_info(counts)')]
        assert after['app_visit'] == before['app_visit'] + 1
        for event in ('generation_success', 'download_click'): assert before[event] == after[event]
        assert columns == ['day', 'event', 'style', 'error', 'count']
        checks.append('reload clears config/content; no browser storage; reload only increments app visit')
        # Separate browser context has no state from the first page.
        other = await browser.new_context(); second = await other.new_page(); await second.goto(url + '/app')
        assert await second.locator('#api-key').input_value() == ''; await other.close()
        assert not errors, errors
        await context.close(); await browser.close()
    result = {'checks': checks, 'javascript_errors': errors, 'accessibility': accessibility, 'statistics': after, 'upstream': 'offline transport double; no real API key used'}
    (artifacts / 'browser-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    with tempfile.TemporaryDirectory(prefix='tuka-browser-') as temporary:
        database = Path(temporary) / 'metrics.sqlite3'
        service.app.config.update(METRICS_DB=str(database), TESTING=False)
        service._rates.clear()
        server = make_server('127.0.0.1', 0, service.app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with patch('ai_providers.safe_request', side_effect=offline_model), patch('main.safe_request', side_effect=offline_image):
                asyncio.run(verify(f'http://127.0.0.1:{server.server_port}', database, temporary))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__': main()
