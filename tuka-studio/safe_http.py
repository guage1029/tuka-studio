"""Bounded HTTPS transport: no proxies, redirects, or second DNS lookup."""
import concurrent.futures
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import quote, urlsplit

MESSAGES = {
    'no_models': '厂商未返回可用于图卡文案的文本模型，请检查账户开通情况。',
    'image_fetch_failed': '正文配图获取失败或格式无效，请移除或替换 Markdown 图片链接后重试。',
    'insufficient_balance': '模型服务账户余额不足，请到所选厂商平台检查余额或充值后重试。',
    'provider_rejected': '模型服务拒绝了当前请求参数，请刷新模型列表或更换模型后重试。',
    'bad_request': '输入或模型配置不正确，请检查后重试。',
    'unsafe_target': '仅支持公网 HTTPS 地址（443 端口），不允许内网或重定向。',
    'auth_failed': '模型鉴权失败，请检查 Key。',
    'model_not_found': '模型不存在或未开通，请刷新模型列表并检查厂商账户权限。',
    'rate_limited': '请求过于频繁，请稍后重试。',
    'timeout': '处理超时，当前内容已保留，请稍后重试。',
    'network': '无法连接指定服务，请检查地址与服务状态。',
    'service_unavailable': '模型服务暂不可用，请稍后重试。',
    'bad_response': '模型返回的内容格式不正确，请重试。',
    'invalid_json': '模型未返回有效 JSON，自动纠正一次后仍失败；正文已保留，请重试或切换模型。',
    'invalid_card_data': '模型返回的卡片字段、字数或页数不符合要求，自动纠正一次后仍失败；正文已保留，请重试或切换模型。',
    'empty_response': '模型未返回文本，请检查模型能力后重试。',
    'truncated': '模型输出被截断，请缩短正文后重试。',
    'too_large': '请求或图片超过大小限制。',
    'busy': '服务正忙，请稍后重试。',
    'render_failed': '图片渲染失败，编辑内容已保留，请重试。',
}


class RequestError(RuntimeError):
    def __init__(self, code, note=None):
        self.code = code
        self.note = note
        message = MESSAGES[code]
        if code == 'invalid_card_data' and note:
            message += f'（{note}）'
        super().__init__(message)

    def to_dict(self):
        return {'code': self.code, 'error': str(self)}


def parse_https_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in url) or '\\' in url:
        raise RequestError('unsafe_target')
    try:
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.port not in (None, 443)
                or parts.username is not None or parts.password is not None or parts.fragment):
            raise ValueError
        parts.hostname.encode('idna')
        return parts
    except (ValueError, UnicodeError):
        raise RequestError('unsafe_target') from None


def public_ip(value):
    ip = ipaddress.ip_address(value)
    return (ip.is_global and not ip.is_multicast and not ip.is_reserved
            and not getattr(ip, 'ipv4_mapped', None)
            and not getattr(ip, 'sixtofour', None) and not getattr(ip, 'teredo', None))


_resolver = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_dns_slots = threading.BoundedSemaphore(4)


def resolve_public(host, timeout):
    if not _dns_slots.acquire(blocking=False):
        raise RequestError('busy')
    future = _resolver.submit(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _dns_slots.release())
    try:
        addresses = list(dict.fromkeys(row[4][0] for row in future.result(timeout=timeout)))
        if not addresses or not all(public_ip(ip) for ip in addresses):
            raise RequestError('unsafe_target')
        return addresses[0]
    except concurrent.futures.TimeoutError:
        raise RequestError('timeout') from None
    except (OSError, ValueError):
        raise RequestError('network') from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address
        self.deadline = time.monotonic() + timeout

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = raw
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise RequestError('timeout')
            raw.settimeout(remaining)
            if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(self.address):
                raise RequestError('unsafe_target')
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def safe_request(url, *, body=None, headers=None, max_bytes=1024 * 1024, timeout=60):
    parts = parse_https_url(url)
    deadline = time.monotonic() + timeout
    host = parts.hostname.encode('idna').decode('ascii')
    address = resolve_public(host, min(5, timeout))
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RequestError('timeout')
    connection = PinnedHTTPSConnection(host, address, remaining)
    expired = threading.Event()

    def abort():
        expired.set()
        if connection.sock:
            try:
                connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()

    timer = threading.Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    try:
        path = quote(parts.path or '/', safe="/%:@-._~!$&'()*+,;=")
        if parts.query:
            path += '?' + quote(parts.query, safe="%=&-._~")
        connection.connect()
        if expired.is_set() or time.monotonic() >= deadline:
            raise RequestError('timeout')
        connection.request('POST' if body is not None else 'GET', path, body=body,
                           headers={'Accept-Encoding': 'identity', **(headers or {})})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise RequestError('unsafe_target')
        if response.getheader('Content-Encoding', 'identity') != 'identity':
            raise RequestError('bad_response')
        size = response.getheader('Content-Length')
        if size is not None and (not size.isdigit() or int(size) > max_bytes):
            raise RequestError('too_large')
        chunks, total = [], 0
        while True:
            if expired.is_set() or time.monotonic() >= deadline:
                raise RequestError('timeout')
            chunk = response.read1(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise RequestError('too_large')
        if size is not None and total != int(size):
            raise RequestError('bad_response')
        if expired.is_set():
            raise RequestError('timeout')
        return response.status, response.getheader('Content-Type', ''), b''.join(chunks)
    except RequestError:
        raise
    except (TimeoutError, socket.timeout):
        raise RequestError('timeout') from None
    except (OSError, http.client.HTTPException, ValueError):
        raise RequestError('timeout' if expired.is_set() else 'network') from None
    finally:
        timer.cancel()
        connection.close()
