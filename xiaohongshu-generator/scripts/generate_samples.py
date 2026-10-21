#!/usr/bin/env python3
"""Generate only first-party sample assets with the production renderer."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from main import ROOT, STYLE_NAMES, capture_slides, render_html

SAMPLE = {
    'cover_title': '给灵感留白', 'cover_subtitle': '让创作成为一种日常，而不是等待灵感的偶然。',
    'cover_tags': ['创作日常', '表达练习', '慢慢积累'], 'cover_image': None,
    'slides': [{'title': '让好想法留下来', 'content': ['把观察记下来，不急着判断价值。',
                '每天十五分钟，只写一个真实的问题。', '先完成，再打磨。为重要的表达留白。'], 'image': None}],
}


async def generate():
    output = ROOT / 'static/samples'
    output.mkdir(exist_ok=True)
    manifest = {'sample': SAMPLE, 'templates': {}}
    for style, name in STYLE_NAMES.items():
        html = render_html(SAMPLE, style)
        cards = await capture_slides(html)
        hashes = []
        for index, raw in enumerate(cards):
            hashes.append(hashlib.sha256(raw).hexdigest())
            image = Image.open(io.BytesIO(raw))
            image.save(output / f'{style}-{"full" if index == 0 else "content"}.webp', quality=88, method=4)
            if index == 0:
                image.thumbnail((372, 497))
                image.save(output / f'{style}.webp', quality=84, method=4)
        manifest['templates'][style] = {'name': name, 'png_sha256': hashes,
            'template_sha256': hashlib.sha256(html.encode()).hexdigest()}
        print(style, flush=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f'Generated {len(STYLE_NAMES)} real template samples.')


if __name__ == '__main__':
    asyncio.run(generate())
