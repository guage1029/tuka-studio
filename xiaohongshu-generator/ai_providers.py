#!/usr/bin/env python3
"""
多提供商 AI 接入层（Gemini / MiniMax / DeepSeek）

设计要点：
1. 统一入口 generate_json(prompt, temperature) -> str，屏蔽各厂商 SDK/HTTP 差异
2. 配置持久化到 ai_config.json（权限 600，不入库），兼容 config.py 里的旧配置
3. 错误分类可读：区分鉴权失败 / 配额耗尽 / 限流 / 模型不存在 / 网络故障 / 服务不可用，
   不再把所有 ResourceExhausted 统一提示成"配额或频率问题"
"""

import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path

import requests

import config

REQUEST_TIMEOUT = 120
CONFIG_PATH = Path(__file__).resolve().parent / "ai_config.json"

PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "kind": "gemini",
        "docs": "https://ai.google.dev/gemini-api/docs",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ],
    },
    "minimax": {
        "label": "MiniMax",
        "kind": "openai_compatible",
        "base_url": "https://api.minimax.io/v1",
        "docs": "https://platform.minimax.io/docs/api-reference/text-chat-openai",
        "models": [
            "MiniMax-M3",
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "docs": "https://api-docs.deepseek.com/",
        "models": [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-flash",
        ],
    },
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = {
    "gemini": "gemini-2.5-flash",
    "minimax": "MiniMax-M2.5",
    "deepseek": "deepseek-v4-flash",
}


class AIProviderError(RuntimeError):
    """带分类和可操作提示的 AI 调用异常"""

    def __init__(self, code: str, message: str, detail: str = "", status: int = None):
        super().__init__(message)
        self.code = code
        self.detail = detail
        self.status = status

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "error": str(self),
            "detail": self.detail,
            "status": self.status,
        }


# --------------------------------------------------------------------------
# 配置持久化
# --------------------------------------------------------------------------

def _default_config() -> dict:
    return {
        "provider": DEFAULT_PROVIDER,
        "models": {},
        "api_keys": {},
    }


def load_config() -> dict:
    """读取已保存的 AI 配置；文件损坏时回退到默认结构而不是崩溃"""
    data = _default_config()
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return data
        if isinstance(stored, dict):
            for key in ("provider", "models", "api_keys"):
                if isinstance(stored.get(key), type(data[key])):
                    data[key] = stored[key]
    if data["provider"] not in PROVIDERS:
        data["provider"] = DEFAULT_PROVIDER
    data["models"] = {k: v for k, v in data["models"].items() if k in PROVIDERS}
    data["api_keys"] = {k: v for k, v in data["api_keys"].items() if k in PROVIDERS and v}
    return data


def save_config(data: dict) -> None:
    """原子写入配置文件并收紧权限（默认 umask 下 json 文件会是 644，密钥不能那样放）"""
    payload = {
        "provider": data.get("provider", DEFAULT_PROVIDER),
        "models": {k: v for k, v in (data.get("models") or {}).items() if k in PROVIDERS},
        "api_keys": {k: v for k, v in (data.get("api_keys") or {}).items() if k in PROVIDERS and v},
    }
    fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_PATH.parent), prefix=".ai_config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, CONFIG_PATH)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def mask_key(key: str) -> str:
    """只回显末 4 位，绝不返回明文"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{'*' * 8}{key[-4:]}"


def get_api_key(provider: str, override: str = None) -> str:
    """取 Key：临时传入 > 已保存 > config.py 旧配置"""
    if override and override.strip():
        return override.strip()
    saved = load_config()["api_keys"].get(provider, "")
    if saved:
        return saved
    if provider == "gemini":
        return getattr(config, "GEMINI_API_KEY", "") or ""
    return ""


def get_model(provider: str, override: str = None) -> str:
    """取模型名：临时传入 > 已保存 > 内置默认"""
    if override and override.strip():
        return override.strip()
    saved = load_config()["models"].get(provider)
    if saved:
        return saved
    return DEFAULT_MODEL.get(provider, PROVIDERS[provider]["models"][0])


def active_provider() -> str:
    return load_config()["provider"]


def provider_public_info() -> list:
    """给前端用的提供商清单：只包含是否已配置 Key 和脱敏值"""
    saved = load_config()
    info = []
    for pid, meta in PROVIDERS.items():
        key = get_api_key(pid)
        info.append({
            "id": pid,
            "label": meta["label"],
            "kind": meta["kind"],
            "models": meta["models"],
            "docs": meta["docs"],
            "has_key": bool(key),
            "key_masked": mask_key(key),
            "model": get_model(pid),
            "is_active": pid == saved["provider"],
        })
    return info


# --------------------------------------------------------------------------
# 错误分类
# --------------------------------------------------------------------------

def _truncate(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text[:limit]


def _classify_status(status: int, body: str, label: str, model: str) -> AIProviderError:
    """把 HTTP 状态码 + 响应体翻译成具体原因"""
    blob = body or ""
    lowered = blob.lower()

    if status in (401, 403):
        return AIProviderError(
            "auth_failed",
            f"{label} 鉴权失败：API Key 无效、已过期或未开通该模型权限。",
            _truncate(blob),
            status,
        )
    if status == 402 or "insufficient balance" in lowered or "insufficient_balance" in lowered:
        return AIProviderError(
            "insufficient_balance",
            f"{label} 账户余额不足，请充值后再试。",
            _truncate(blob),
            status,
        )
    if status == 429:
        if "quota" in lowered or "exceeded" in lowered or "rate limit" in lowered:
            return AIProviderError(
                "quota_exhausted",
                f"{label} 配额已用尽或触发限流，请稍后重试或更换模型。",
                _truncate(blob),
                status,
            )
        return AIProviderError(
            "rate_limited",
            f"{label} 请求过于频繁（429），请降低并发或稍后重试。",
            _truncate(blob),
            status,
        )
    if status == 404:
        return AIProviderError(
            "model_not_found",
            f"{label} 返回 404：模型名或接口地址不正确。当前模型：{model}",
            _truncate(blob),
            status,
        )
    if status == 400:
        return AIProviderError(
            "bad_request",
            f"{label} 拒绝了该请求（400），通常是模型名不支持或参数不被接受。",
            _truncate(blob),
            status,
        )
    if status >= 500:
        return AIProviderError(
            "service_unavailable",
            f"{label} 服务端异常（{status}），通常是上游临时故障，稍后重试。",
            _truncate(blob),
            status,
        )
    return AIProviderError(
        "http_error",
        f"{label} 调用失败（HTTP {status}）。",
        _truncate(blob),
        status,
    )


def _classify_request_exception(exc: Exception, label: str) -> AIProviderError:
    name = type(exc).__name__
    text = _truncate(str(exc))
    if name in ("Timeout", "ReadTimeout", "ConnectTimeout", "DeadlineExceeded"):
        return AIProviderError(
            "timeout",
            f"{label} 请求超时（{REQUEST_TIMEOUT}秒）。请检查网络或代理是否可用。",
            text,
        )
    if name in ("ProxyError", "SSLError", "ConnectionError", "NewConnectionError"):
        return AIProviderError(
            "network",
            f"无法连接 {label}（{text}）。请检查 https_proxy 是否指向可用代理。",
            text,
        )
    return AIProviderError("network", f"{label} 网络异常（{name}）。", text)


def classify_gemini_exception(exc: Exception, model: str) -> AIProviderError:
    """Gemini SDK 异常分类，并把原始 quota 细节透出来（区分模型级配额与 RPM 限流）"""
    name = type(exc).__name__
    text = _truncate(str(exc), 800)
    lowered = text.lower()

    if name in ("DeadlineExceeded", "ReadTimeout", "Timeout", "ConnectTimeout"):
        return AIProviderError(
            "timeout",
            f"Gemini 请求超时（{REQUEST_TIMEOUT}秒）。请确认代理可用："
            "curl -x http://127.0.0.1:7897 https://generativelanguage.googleapis.com",
            text,
        )
    if name in ("ProxyError", "SSLError", "ConnectionError", "NewConnectionError"):
        return AIProviderError("network", f"无法连接 Gemini（{text}）。请检查 https_proxy 设置。", text)
    if name in ("ServiceUnavailable", "InternalServerError", "Unknown"):
        return AIProviderError(
            "service_unavailable",
            f"Gemini 暂时不可用（{name}）。通常是网络无法直连 Google，"
            "请设置代理：https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 ./start.sh",
            text,
        )
    if name == "ResourceExhausted":
        per_day = "per day" in lowered or "daily" in lowered or "天" in text
        per_minute = "per minute" in lowered or "rpm" in lowered
        if per_day:
            hint = (
                f"Gemini 模型 {model} 的免费层每日配额已用尽（该配额按模型分别计算）。"
                "等待配额重置，或在设置里切换到其他模型/提供商。"
            )
        elif per_minute:
            hint = f"Gemini 模型 {model} 触发每分钟请求数限制（RPM），降低调用频率即可。"
        else:
            hint = f"Gemini 模型 {model} 配额已用尽或被限流。"
        return AIProviderError("quota_exhausted", hint, text)
    if name in ("PermissionDenied", "Unauthenticated"):
        return AIProviderError(
            "auth_failed",
            "Gemini API Key 无效或未启用 Gemini API，请在设置里检查 Key。",
            text,
        )
    if name == "NotFound":
        return AIProviderError(
            "model_not_found",
            f"Gemini 模型不存在或当前 Key 无权访问：{model}",
            text,
        )
    return AIProviderError("unknown", f"Gemini 调用失败：{name}: {text}", text)


# --------------------------------------------------------------------------
# 生成实现
# --------------------------------------------------------------------------

def _request_options():
    from google.generativeai.types import RequestOptions
    return RequestOptions(timeout=REQUEST_TIMEOUT)


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\s*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def _gemini_text(response) -> str:
    """
    安全取文本。思考型模型在小 max_output_tokens 下会返回"没有有效 Part"的响应，
    此时 response.text quick accessor 会抛 InvalidOperation，必须逐 candidate 兜底取。
    """
    try:
        text = response.text
        if text:
            return text
    except Exception:
        pass

    chunks = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _gemini_generate(prompt: str, api_key: str, model_name: str, temperature: float,
                     max_output_tokens: int = None, json_mode: bool = True) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel(model_name)
        generation_config = {"temperature": temperature}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        if max_output_tokens:
            generation_config["max_output_tokens"] = max_output_tokens

        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(**generation_config),
            request_options=_request_options(),
        )
    except Exception as exc:
        raise classify_gemini_exception(exc, model_name) from exc

    text = _gemini_text(response)
    if not text.strip():
        raise AIProviderError(
            "empty_response",
            f"Gemini 模型 {model_name} 返回了空内容。若是思考型模型，通常是 "
            "max_output_tokens 太小被思考过程占满，换用非思考模型或调大额度。",
            _truncate(str(getattr(response, "candidates", ""))),
        )
    return _strip_fence(text)


def _openai_compatible_generate(prompt: str, meta: dict, api_key: str, base_url: str,
                                model_name: str, temperature: float,
                                max_output_tokens: int = 8192) -> str:
    label = meta["label"]
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_completion_tokens": max_output_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout as exc:
        raise AIProviderError(
            "timeout",
            f"{label} 请求超时（{REQUEST_TIMEOUT}秒）。请检查网络或代理是否可用。",
            _truncate(str(exc)),
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise _classify_request_exception(exc, label) from exc

    if resp.status_code != 200:
        raise _classify_status(resp.status_code, resp.text, label, model_name)

    try:
        payload = resp.json()
        return _strip_fence(payload["choices"][0]["message"].get("content") or "")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIProviderError(
            "bad_response",
            f"{label} 返回了无法解析的响应结构：{exc}",
            _truncate(resp.text),
            resp.status_code,
        ) from exc


def generate_json(prompt: str, temperature: float = 0.7, provider: str = None,
                  api_key: str = None, model: str = None) -> str:
    """
    统一生成入口，返回（已剥离代码块标记的）文本。
    调用方负责 json.loads。
    """
    provider = provider or active_provider()
    if provider not in PROVIDERS:
        raise AIProviderError("unknown_provider", f"未知提供商：{provider}")

    meta = PROVIDERS[provider]
    model_name = get_model(provider, model)
    key = get_api_key(provider, api_key)
    if not key:
        raise AIProviderError(
            "missing_api_key",
            f"尚未配置 {meta['label']} 的 API Key，请先在页面设置中填写。",
        )

    if meta["kind"] == "gemini":
        return _gemini_generate(prompt, key, model_name, temperature)
    return _openai_compatible_generate(
        prompt, meta, key, meta["base_url"], model_name, temperature
    )


# --------------------------------------------------------------------------
# 连通性测试 / 模型列表
# --------------------------------------------------------------------------

def test_connection(provider: str, api_key: str = None, model: str = None) -> dict:
    """
    用最小生成请求验证 Key + 模型 + 配额。
    只做一次极短调用：GET /models 只能证明 Key 有效，无法发现配额耗尽。
    """
    if provider not in PROVIDERS:
        raise AIProviderError("unknown_provider", f"未知提供商：{provider}")

    meta = PROVIDERS[provider]
    key = get_api_key(provider, api_key)
    if not key:
        raise AIProviderError(
            "missing_api_key",
            f"尚未配置 {meta['label']} 的 API Key，请先填写。",
        )

    model_name = get_model(provider, model)
    started = time.time()

    if meta["kind"] == "gemini":
        text = _gemini_generate(
            "只回复 OK 两个字符，不要其他内容。",
            key,
            model_name,
            temperature=0.0,
            max_output_tokens=512,
            json_mode=False,
        )
    else:
        text = _openai_compatible_generate(
            "只回复 OK 两个字符，不要其他内容。",
            meta,
            key,
            meta["base_url"],
            model_name,
            temperature=0.0,
            max_output_tokens=256,
        )

    elapsed = time.time() - started
    return {
        "provider": provider,
        "label": meta["label"],
        "model": model_name,
        "reply": _truncate(text, 120),
        "latency_ms": int(elapsed * 1000),
    }


GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL_LIST_TIMEOUT = 30
# 模型目录变化很慢，但每次查询都可能因代理分页而耗时数十秒，缓存 10 分钟避免每次开页面都等
_MODEL_CACHE_TTL = 600
_model_cache = {}


def _cache_key(provider: str, api_key: str) -> str:
    import hashlib
    return f"{provider}:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"


def list_remote_models(provider: str, api_key: str = None) -> list:
    """查询上游实际可用模型；失败时抛 AIProviderError，由调用方回退到静态清单"""
    if provider not in PROVIDERS:
        raise AIProviderError("unknown_provider", f"未知提供商：{provider}")

    meta = PROVIDERS[provider]
    key = get_api_key(provider, api_key)
    if not key:
        raise AIProviderError("missing_api_key", f"尚未配置 {meta['label']} 的 API Key。")

    cache_id = _cache_key(provider, key)
    cached = _model_cache.get(cache_id)
    if cached and time.time() - cached[0] < _MODEL_CACHE_TTL:
        return cached[1]

    if meta["kind"] == "gemini":
        # 走一次性 REST 而不是 genai.list_models()：SDK 走分页，代理下单次可耗时 40s+
        try:
            resp = requests.get(
                GEMINI_MODELS_URL,
                params={"key": key, "pageSize": 200},
                timeout=MODEL_LIST_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise _classify_request_exception(exc, meta["label"]) from exc
        if resp.status_code != 200:
            raise _classify_status(resp.status_code, resp.text, meta["label"], "v1beta/models")
        names = [
            item.get("name", "").split("/", 1)[1]
            for item in resp.json().get("models", [])
            if "generateContent" in (item.get("supportedGenerationMethods") or [])
            and "/" in item.get("name", "")
        ]
        models = sorted(set(names))
    else:
        url = f"{meta['base_url'].rstrip('/')}/models"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=MODEL_LIST_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise _classify_request_exception(exc, meta["label"]) from exc
        if resp.status_code != 200:
            raise _classify_status(resp.status_code, resp.text, meta["label"], url)
        models = sorted(item.get("id") for item in resp.json().get("data", []) if item.get("id"))

    if not models:
        raise AIProviderError(
            "empty_model_list",
            f"{meta['label']} 未返回任何可用模型，请确认 Key 有该模型权限。",
        )
    _model_cache[cache_id] = (time.time(), models)
    return models