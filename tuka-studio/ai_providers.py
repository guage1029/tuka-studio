"""Domestic providers with fixed endpoints and request-scoped credentials."""
import json
import re
from safe_http import RequestError, safe_request

AIProviderError = RequestError
REQUEST_TIMEOUT = 60


# Checked against official documentation on 2026-10-21; see PROVIDERS.md.
PROVIDERS = {
    'deepseek': {'name': 'DeepSeek', 'protocol': 'openai', 'base_url': 'https://api.deepseek.com',
                 'models_path': '/models', 'prefixes': ('deepseek-',)},
    'minimax': {'name': 'MiniMax', 'protocol': 'anthropic', 'base_url': 'https://api.minimax.cn/anthropic/v1',
                'models': ('MiniMax-M3', 'MiniMax-M3.1-Flash')},
    'kimi': {'name': 'Kimi（月之暗面）', 'protocol': 'openai', 'base_url': 'https://api.moonshot.cn/v1',
             'models_path': '/models', 'prefixes': ('kimi-', 'moonshot-')},
    'zhipu': {'name': '智谱 GLM', 'protocol': 'openai', 'base_url': 'https://open.bigmodel.cn/api/paas/v4',
              'models': ('glm-5.3', 'glm-5.3-flash', 'glm-5.3-flashx', 'glm-5.2', 'glm-4.7-flash', 'glm-4.5-flash')},
    'doubao': {'name': '豆包（火山方舟）', 'protocol': 'openai', 'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
               'models': ('doubao-seed-2-1-lite-260915', 'doubao-seed-2-1-pro-260915',
                          'doubao-seed-2-1-turbo-260628', 'doubao-seed-2-0-mini-260428')},
    'qwen': {'name': '阿里云百炼（通义千问）', 'protocol': 'openai', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
             'models': ('qwen3.8-max', 'qwen3.8-flash', 'qwen3.7-plus', 'qwen-plus')},
    'qianfan': {'name': '百度千帆（文心 ERNIE）', 'protocol': 'openai', 'base_url': 'https://qianfan.baidubce.com/v2',
                'models_path': '/models', 'prefixes': ('ernie-',), 'model_owner': 'Baidu',
                'model_types': ('chat', 'multimodal'), 'model_endpoint': '/v2/chat/completions'},
    'hunyuan': {'name': '腾讯混元（TokenHub）', 'protocol': 'openai', 'base_url': 'https://tokenhub.tencentmaas.com/v1',
                'models_path': '/models', 'exact_models': ('hy3', 'hy4'),
                'prefixes': ('hy4-', 'hy-mt2-', 'hy-role', 'hunyuan-role-'),
                'online_only': True},
}
CATALOG_DATE = '2026-10-21'
MODEL_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z')


def validate_credentials(provider, api_key):
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise RequestError('bad_request')
    if (not isinstance(api_key, str) or not 1 <= len(api_key) <= 512
            or not all(33 <= ord(c) <= 126 for c in api_key)):
        raise RequestError('bad_request')
    return PROVIDERS[provider]


def valid_model(provider, model):
    if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
        return False
    if 'models' in provider:
        return model in provider['models']
    return model in provider.get('exact_models', ()) or (model.startswith(provider['prefixes']) and not any(
        word in model.lower() for word in ('embedding', 'rerank', 'audio', 'tts', 'whisper'))
    )


def validate_config(config):
    if not isinstance(config, dict) or set(config) != {'provider', 'api_key', 'model'}:
        raise RequestError('bad_request')
    provider = validate_credentials(config['provider'], config['api_key'])
    if not valid_model(provider, config['model']):
        raise RequestError('bad_request')
    return dict(config)


def check_status(status):
    if status != 200:
        code = {400: 'provider_rejected', 401: 'auth_failed', 402: 'insufficient_balance',
                403: 'auth_failed', 404: 'model_not_found', 422: 'provider_rejected',
                408: 'timeout', 429: 'rate_limited'}.get(status,
                       'service_unavailable' if status >= 500 else 'bad_response')
        raise RequestError(code)


def list_models(provider_id, api_key):
    provider = validate_credentials(provider_id, api_key)
    if 'models' in provider:
        # shortcut: no documented API-Key-only discovery; update the public catalog when providers change it.
        return {'models': list(provider['models']), 'source': 'catalog', 'updated': CATALOG_DATE}
    status, _, raw = safe_request(provider['base_url'] + provider['models_path'],
        headers={'Authorization': 'Bearer ' + api_key}, timeout=15)
    check_status(status)
    try:
        data = json.loads(raw)['data']
        if not isinstance(data, list) or len(data) > 500:
            raise RequestError('bad_response')
        models = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise RequestError('bad_response')
            architecture = item.get('architecture', {})
            if not isinstance(architecture, dict):
                raise RequestError('bad_response')
            modalities = item.get('output_modalities', architecture.get('output_modalities', ['text']))
            if not isinstance(modalities, list) or not all(isinstance(value, str) for value in modalities):
                raise RequestError('bad_response')
            if provider.get('model_owner') and item.get('owned_by') != provider['model_owner']:
                continue
            if provider.get('model_types') and item.get('type') not in provider['model_types']:
                continue
            if provider.get('model_endpoint'):
                endpoints = item.get('endpoints')
                if not isinstance(endpoints, list) or not all(isinstance(value, str) for value in endpoints):
                    raise RequestError('bad_response')
                if provider['model_endpoint'] not in endpoints:
                    continue
            if provider.get('online_only') and item.get('status') != 'online':
                continue
            if (valid_model(provider, item['id']) and 'text' in modalities
                    and item['id'] not in models):
                models.append(item['id'])
    except (KeyError, TypeError, ValueError):
        raise RequestError('bad_response') from None
    if not models:
        raise RequestError('no_models')
    return {'models': models, 'source': 'live'}


def generate_json(prompt, config, *, timeout=REQUEST_TIMEOUT):
    config = validate_config(config)
    provider = PROVIDERS[config['provider']]
    anthropic = provider['protocol'] == 'anthropic'
    payload = {'model': config['model'], 'messages': [{'role': 'user', 'content': prompt}]}
    headers = {'Content-Type': 'application/json'}
    if anthropic:
        payload['max_tokens'] = 4096
        endpoint = '/messages'
        headers.update({'Authorization': 'Bearer ' + config['api_key'], 'anthropic-version': '2023-06-01'})
    else:
        endpoint = '/chat/completions'
        headers['Authorization'] = 'Bearer ' + config['api_key']
        if config['provider'] == 'deepseek':
            payload['response_format'] = {'type': 'json_object'}
    status, _, raw = safe_request(provider['base_url'] + endpoint,
                                  body=json.dumps(payload, ensure_ascii=False).encode(),
                                  headers=headers, timeout=min(timeout, REQUEST_TIMEOUT))
    check_status(status)
    try:
        response = json.loads(raw)
        if anthropic:
            if response.get('stop_reason') in ('max_tokens', 'model_context_window_exceeded'):
                raise RequestError('truncated')
            text = ''.join(block['text'] for block in response['content'] if block.get('type') == 'text')
        else:
            choice = response['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise RequestError('truncated')
            text = choice['message']['content']
        if not isinstance(text, str) or not text.strip():
            raise RequestError('empty_response')
        text = text.strip()
        fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced[1]
        try:
            result = json.loads(text)
        except ValueError:
            raise RequestError('invalid_json') from None
        if not isinstance(result, dict):
            raise RequestError('invalid_json')
        return result
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise RequestError('bad_response') from None
