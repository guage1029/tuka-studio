#!/usr/bin/env python3
"""Public card tool: request-scoped secrets, in-memory images and bounded work."""
import asyncio
import base64
from collections import OrderedDict, deque
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import gzip
import hmac
import io
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import zipfile

from flask import Flask, Request, jsonify, make_response, render_template, request, send_file
from PIL import Image
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import ai_providers
import main
import metrics
from safe_http import RequestError


class MemoryRequest(Request):
    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        # Werkzeug's default stream spills uploads larger than 500 KiB to disk.
        return io.BytesIO()


app = Flask(__name__)
app.request_class = MemoryRequest
trusted_hosts = ['tuka.guage.chat']
if os.environ.get('TRUST_LOCAL_PROXY') != '1':
    trusted_hosts.extend(('localhost', '127.0.0.1'))
app.config.update(MAX_CONTENT_LENGTH=32 * 1024 * 1024,
                  MAX_FORM_PARTS=4,
                  METRICS_DB=os.environ.get('METRICS_DB', str(metrics.DEFAULT_DB)),
                  TRUSTED_HOSTS=trusted_hosts)
# Only enable behind the local reverse proxy described in DEPLOYMENT.md.
if os.environ.get('TRUST_LOCAL_PROXY') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
_HEAVY = threading.BoundedSemaphore(2)
_RENDER = threading.BoundedSemaphore(1)
_rate_lock = threading.Lock()
_rates = OrderedDict()
_rate_secret = secrets.token_bytes(32)
HEAVY_PATHS = {'/preview', '/regenerate-slide', '/render', '/regenerate-style', '/download-all', '/upload-image', '/api/models'}


def count(event, style='', error=''):
    try:
        metrics.record(app.config['METRICS_DB'], event, style, error)
    except (OSError, sqlite3.Error):
        app.logger.warning('Anonymous counter unavailable')


def count_card_set():
    try:
        metrics.record_card_set(app.config['METRICS_DB'])
    except (OSError, sqlite3.Error):
        app.logger.warning('Anonymous card set counter unavailable')


def visitor_response(response):
    visitor_id = request.cookies.get('tuka_visitor', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,64}', visitor_id):
        visitor_id = secrets.token_urlsafe(32)
    try:
        metrics.record_visitor(app.config['METRICS_DB'], visitor_id)
    except (OSError, sqlite3.Error):
        app.logger.warning('Anonymous visitor counter unavailable')
    response.set_cookie('tuka_visitor', visitor_id, max_age=315360000,
                        httponly=True, secure=request.is_secure, samesite='Lax', path='/')
    return response


@contextmanager
def slot(semaphore):
    if not semaphore.acquire(blocking=False):
        raise RequestError('busy')
    try:
        yield
    finally:
        semaphore.release()


def rate_limit():
    now = time.monotonic()
    category = 'heavy' if request.path in HEAVY_PATHS else 'events'
    digest = hmac.new(_rate_secret, (request.remote_addr or '').encode(), hashlib.sha256).digest()
    with _rate_lock:
        for key in list(_rates):
            if not _rates[key] or _rates[key][-1] <= now - 60:
                del _rates[key]
        key = (digest, category)
        queue = _rates.setdefault(key, deque())
        while queue and queue[0] <= now - 60:
            queue.popleft()
        if len(queue) >= (12 if category == 'heavy' else 120):
            raise RequestError('rate_limited')
        queue.append(now)
        _rates.move_to_end(key)
        while len(_rates) > 2048:
            _rates.popitem(last=False)


@app.before_request
def protect_request():
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin != request.host_url.rstrip('/')):
            return jsonify(error='仅允许同源请求。', code='bad_request'), 403
        rate_limit()


@app.after_request
def privacy_headers(response):
    response.headers.update({
        'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    })
    return response


@app.errorhandler(RequestError)
def expected_error(exc):
    status = {'bad_request': 400, 'unsafe_target': 400, 'too_large': 413,
              'auth_failed': 401, 'insufficient_balance': 402, 'model_not_found': 404, 'timeout': 504,
              'image_fetch_failed': 422,
              'rate_limited': 429, 'busy': 503}.get(exc.code, 502)
    response = jsonify(exc.to_dict())
    if status in (429, 503):
        response.headers['Retry-After'] = '60'
    return response, status


@app.errorhandler(Exception)
def unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error='请求无效或资源不存在。', code='too_large' if exc.code == 413 else 'bad_request'), exc.code
    app.logger.error('Request failed; details suppressed for privacy')
    return jsonify(error='处理失败，当前内容已保留，请重试。', code='service_unavailable'), 500


def payload(allowed, required=()):
    data = request.get_json()
    if not isinstance(data, dict) or not set(data) <= set(allowed) or not set(required) <= set(data):
        raise RequestError('bad_request')
    return data


DARK_STYLES = {'tech', 'streaming', 'capsule', 'ppt-catppuccin-mocha', 'ppt-dracula',
               'ppt-tokyo-night', 'ppt-nord', 'ppt-gruvbox-dark', 'ppt-rose-pine',
               'ppt-glassmorphism', 'ppt-terminal-green', 'ppt-aurora', 'ppt-blueprint',
               'ppt-cyberpunk-neon', 'ppt-vaporwave'}

LEGACY_STYLE_PALETTES = {
    'xiaohongshu': ('#ffffff', '#111111', '#ff4258', '#ffd1ff'),
    'apple': ('#f5f5f7', '#1d1d1f', '#0071e3', '#6e6e73'),
    'neobrutalist': ('#dfff00', '#000000', '#ff3131', '#0066ff'),
    'chinese': ('#fdfbf7', '#3d2817', '#c04851', '#8fb2c9'),
    'memphis': ('#ffffff', '#000000', '#ffd700', '#4ecdc4'),
    'journal': ('#fdf8f3', '#5d4e37', '#ffb6c1', '#98d8c8'),
    'magazine': ('#ffffff', '#000000', '#111111', '#888888'),
    'polaroid': ('#fafafa', '#333333', '#dddddd', '#666666'),
    'tech': ('#1a1a2e', '#ffffff', '#667eea', '#764ba2'),
    'streaming': ('#0a0a0a', '#ffffff', '#6366f1', '#ec4899'),
    'capsule': ('#1a1a1a', '#33ff00', '#33ff00', '#ffffff'),
}


@lru_cache(maxsize=None)
def style_palette(style):
    if style in LEGACY_STYLE_PALETTES:
        values = LEGACY_STYLE_PALETTES[style]
    else:
        css = (main.ROOT / 'themes' / f'{style[4:]}.css').read_text()
        values = tuple(re.search(rf'--{token}\s*:\s*(#[0-9a-fA-F]{{3,8}})', css).group(1)
                       for token in ('bg', 'text-1', 'accent', 'accent-2'))
    return dict(zip(('background', 'foreground', 'accent', 'accent_secondary'), values))


def styles():
    # shortcut: unlisted styles default to light, classify them when adding a dark theme.
    return [{'id': style, 'name': name, 'group': 'dark' if style in DARK_STYLES else 'light',
             'palette': style_palette(style)}
            for style, name in main.STYLE_NAMES.items()]


@app.get('/')
def index():
    count('home_visit')
    response = visitor_response(make_response(''))
    try:
        totals = metrics.public_totals(app.config['METRICS_DB'])
    except sqlite3.Error:
        app.logger.warning('Anonymous totals unavailable')
        totals = {'unique_browsers': 0, 'card_sets': 0}
    response.set_data(render_template('index.html', styles=styles(), totals=totals))
    return response


@app.get('/app')
def workspace():
    style = request.args.get('style', 'xiaohongshu')
    main.validate_style(style)
    count('app_visit')
    response = make_response(render_template('app.html', styles=styles(), selected_style=style, providers=ai_providers.PROVIDERS))
    return visitor_response(response)


@app.post('/api/models')
def model_list():
    data = payload(('provider', 'api_key'), ('provider', 'api_key'))
    with slot(_HEAVY):
        return jsonify(success=True, **ai_providers.list_models(data['provider'], data['api_key']))


@app.post('/api/events')
def event():
    data = payload(('event', 'style'), ('event',))
    event, style = data['event'], data.get('style', '')
    if not isinstance(event, str) or event not in metrics.CLIENT_EVENTS or not isinstance(style, str):
        raise RequestError('bad_request')
    main.validate_style(style)
    count(event, style)
    return '', 204


@app.post('/preview')
def preview():
    data = payload(('content', 'config', 'style'), ('content', 'config', 'style'))
    content = main.text_field(data['content'], 20000)
    if len(content) < 50:
        raise RequestError('bad_request')
    style = main.validate_style(data['style'])
    config = ai_providers.validate_config(data['config'])
    with slot(_HEAVY):
        count('generation_start', style)
        try:
            result = main.summarize_to_slides(content, config)
        except BaseException as exc:
            count('generation_failure', style, exc.code if isinstance(exc, RequestError) else 'service_unavailable')
            raise
        count('generation_success', style)
        count_card_set()
    image_summary = result.pop('image_summary', None)
    draft_issues = result.pop('draft_issues', [])
    return jsonify(success=True, slides_data=result, image_summary=image_summary, draft_issues=draft_issues)


@app.post('/regenerate-slide')
def regenerate_slide():
    data = payload(('slides_data', 'slide_index', 'config', 'style'), ('slides_data', 'slide_index', 'config', 'style'))
    style = main.validate_style(data['style'])
    config = ai_providers.validate_config(data['config'])
    index = data['slide_index']
    with slot(_HEAVY):
        slides = main.validate_slides_data(data['slides_data'])
        if type(index) is not int or not 0 <= index <= len(slides['slides']):
            raise RequestError('bad_request')
        count('generation_start', style)
        try:
            result = main.regenerate_slide(slides, index, config)
        except BaseException as exc:
            count('generation_failure', style, exc.code if isinstance(exc, RequestError) else 'service_unavailable')
            raise
        count('generation_success', style)
    return jsonify(success=True, slides_data=result)


@app.post('/render')
@app.post('/regenerate-style')
def render():
    data = payload(('slides_data', 'style'), ('slides_data', 'style'))
    style = main.validate_style(data['style'])
    with slot(_HEAVY), slot(_RENDER):
        html = main.render_html(data['slides_data'], style)
        try:
            images = asyncio.run(main.capture_slides(html))
        except Exception:
            raise RequestError('render_failed') from None
    response = jsonify(success=True, count=len(images), images=[
        {'filename': f'card-{index + 1:02}.png', 'data': 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')}
        for index, image in enumerate(images)])
    response.vary.add('Accept-Encoding')
    if request.accept_encodings['gzip'] > 0:
        compressed = gzip.compress(response.get_data(), compresslevel=1, mtime=0)
        if len(compressed) < response.content_length:
            response.set_data(compressed)
            response.headers['Content-Encoding'] = 'gzip'
    return response


@app.post('/upload-image')
def upload_image():
    with slot(_HEAVY):
        if request.mimetype == 'multipart/form-data':
            file = request.files.get('file')
            if file is None:
                raise RequestError('bad_request')
            raw = main.image_bytes(file.read(main.MAX_IMAGE_BYTES + 1))
            image = 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
        else:
            data = payload(('image_data',), ('image_data',))
            image = main.data_image(data['image_data'])
    return jsonify(success=True, image_data=image)


@app.post('/download-all')
def download_all():
    data = payload(('images',), ('images',))
    images = data['images']
    if not isinstance(images, list) or not 1 <= len(images) <= main.MAX_CARDS:
        raise RequestError('bad_request')
    with slot(_HEAVY):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
            for index, image in enumerate(images):
                if not isinstance(image, str) or not image.startswith('data:image/png;base64,') or len(image) > 4 * 1024 * 1024:
                    raise RequestError('bad_request')
                try:
                    raw = base64.b64decode(image.split(',', 1)[1], validate=True)
                    with Image.open(io.BytesIO(raw)) as bitmap:
                        if bitmap.format != 'PNG' or bitmap.size != (1242, 1660) or getattr(bitmap, 'is_animated', False):
                            raise RequestError('bad_request')
                        bitmap.verify()
                except (ValueError, OSError):
                    raise RequestError('bad_request') from None
                archive.writestr(f'card-{index + 1:02}.png', raw)
        output.seek(0)
    return send_file(output, mimetype='application/zip', as_attachment=True, download_name='tuka-cards.zip', max_age=0)


if __name__ == '__main__':
    import logging
    logging.getLogger('werkzeug').disabled = True
    app.run(debug=False, host='127.0.0.1', port=5001, threaded=True)
