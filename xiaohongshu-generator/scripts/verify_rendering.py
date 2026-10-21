#!/usr/bin/env python3
"""Render all 46 templates and inspect long text/image layout in Chromium."""
import asyncio
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright
from main import ROOT, STYLE_NAMES, capture_slides, render_html
from scripts.generate_samples import SAMPLE


async def verify():
    artifacts = ROOT / 'output/playwright'
    artifacts.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'static/samples/manifest.json').read_text())
    before = {path.name for path in (ROOT / 'output').iterdir()}
    buffer = io.BytesIO()
    photo = Image.new('RGB', (800, 400), '#e7d7be')
    draw = ImageDraw.Draw(photo); draw.ellipse((300, 60, 620, 380), fill='#b75e4a'); draw.rectangle((130, 110, 350, 330), fill='#526354')
    photo.save(buffer, 'PNG')
    edge = copy.deepcopy(SAMPLE)
    edge.update(cover_title='给每一个认真创作的人留下一点自由表达与思考的空间',
                cover_subtitle=('从每天十五分钟的观察开始，把真实的想法整理成清晰的表达。' * 3)[:80],
                cover_tags=['创作日常表达练习慢积累'[:10]] * 5)
    edge['cover_title'] = edge['cover_title'][:24]
    edge['cover_image'] = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
    edge['slides'][0].update(title='在日常创作里发现并记录那些容易被忽略的真实细节'[:24],
                            content=[('把每天看到的细节和突然冒出的想法记下来，不急着判断价值，用具体故事支撑自己的观点。' * 2)[:50]] * 5,
                            image=edge['cover_image'])
    overflows, results, blocked = [], [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(java_script_enabled=False, service_workers='block', viewport={'width': 1400, 'height': 1800})
            async def block(route):
                blocked.append(route.request.url); await route.abort()
            await context.route('**/*', block)
            page = await context.new_page()
            for style in STYLE_NAMES:
                html = render_html(SAMPLE, style)
                assert hashlib.sha256(html.encode()).hexdigest() == manifest['templates'][style]['template_sha256'], style
                cards = await capture_slides(html)
                assert len(cards) == 2
                for index, raw in enumerate(cards):
                    assert Image.open(io.BytesIO(raw)).size == (1242, 1660), style
                    assert hashlib.sha256(raw).hexdigest() == manifest['templates'][style]['png_sha256'][index], style + ': sample differs'
                await page.set_content(render_html(edge, style), wait_until='load')
                await page.evaluate('document.fonts.ready')
                issues = await page.evaluate('''() => {
                  const issues=[];
                  // Measure flow before the decorative Polaroid rotation; rotated bounding boxes overlap.
                  const frames=[...document.querySelectorAll('.polaroid-frame')];
                  const transforms=frames.map(el=>el.style.transform);
                  frames.forEach(el=>el.style.transform='none');
                  for (const card of document.querySelectorAll('[id^="card-"]')) {
                    const boundary=card.getBoundingClientRect();
                    const elements=card.querySelectorAll('.cover-title,.cover-subtitle,.cover-tag,.pill,.slide-title,.content-text,.item-text,.content-item:not(:has(*))');
                    for (const el of elements) {
                      const range=document.createRange();range.selectNodeContents(el);
                      for (const rect of range.getClientRects()) {
                        const picture=card.querySelector('.image-container')?.getBoundingClientRect();
                        if(picture&&rect.bottom>picture.top+2&&rect.top<picture.bottom-2&&rect.right>picture.left&&rect.left<picture.right) {
                          issues.push({card:card.id,element:el.className,text:el.textContent.trim().slice(0,20),overlap:'image'});break;
                        }
                        let ancestor=el.parentElement;
                        while(ancestor&&ancestor!==card){
                          const box=ancestor.getBoundingClientRect(), css=getComputedStyle(ancestor);
                          if(['hidden','clip'].includes(css.overflowY)&&rect.bottom>box.bottom+2){
                            issues.push({card:card.id,element:el.className,clipped:ancestor.className});break;
                          }
                          ancestor=ancestor.parentElement;
                        }
                        if(rect.left<boundary.left-2||rect.right>boundary.right+2||rect.top<boundary.top-2||rect.bottom>boundary.bottom-24) {
                          issues.push({card:card.id,element:el.className,text:el.textContent.trim().slice(0,20),bottom:Math.round(rect.bottom-boundary.top)});break;
                        }
                      }
                    }
                    for (const img of card.querySelectorAll('img')) {
                      if(!img.complete||!img.naturalWidth) issues.push({card:card.id,image:'not loaded'});
                      const r=img.getBoundingClientRect();if(r.bottom>boundary.bottom-16||r.top<boundary.top) issues.push({card:card.id,image:'outside card',bottom:Math.round(r.bottom-boundary.top)});if(r.height<80) issues.push({card:card.id,image:'too short',height:r.height});
                    }
                  }
                  frames.forEach((el,i)=>el.style.transform=transforms[i]);
                  return issues;
                }''')
                if issues: overflows.append({'style': style, 'issues': issues})
                await page.locator('#card-2').screenshot(path=artifacts / f'edge-{style}.png')
                results.append({'style': style, 'size': [1242, 1660], 'sample_matches': True, 'edge_issues': len(issues)})
                print(style, 'layout issues:', len(issues), flush=True)
            await context.close()
        finally:
            await browser.close()
    assert {path.name for path in (ROOT / 'output').iterdir()} == before, 'Unexpected output file'
    assert not (ROOT / '_temp_render.html').exists()
    report = {'templates': results, 'overflows': overflows, 'external_requests': blocked}
    (artifacts / 'render-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    assert not blocked, blocked
    assert not overflows, json.dumps(overflows, ensure_ascii=False)
    print('All 46 templates: independent render, exact samples, bounded edge layout, zero external requests.')


if __name__ == '__main__': asyncio.run(verify())
