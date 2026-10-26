import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from datetime import timedelta
import hashlib
import gzip
import io
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import zipfile

from PIL import Image
import ai_providers
import app as service
import main
import metrics
import safe_http
from safe_http import RequestError
from scripts.generate_samples import SAMPLE

CONFIG = {'provider': 'deepseek', 'api_key': 'test-only-key', 'model': 'deepseek-flash'}


def bitmap(size=(80, 50), fmt='PNG'):
    output = io.BytesIO(); Image.new('RGB', size, '#ba5745').save(output, fmt)
    return output.getvalue()


def data_url(raw):
    return 'data:image/png;base64,' + base64.b64encode(raw).decode()


class ProtocolTests(unittest.TestCase):
    def response(self, protocol, text, reason=None):
        if protocol == 'anthropic':
            return {'content': [{'type': 'text', 'text': text}], 'stop_reason': reason or 'end_turn'}
        return {'choices': [{'message': {'content': text}, 'finish_reason': reason or 'stop'}]}

    def test_provider_payload_and_fixed_domestic_credentials(self):
        expected = {
            'deepseek': ('openai', 'https://api.deepseek.com/chat/completions'),
            'minimax': ('anthropic', 'https://api.minimax.cn/anthropic/v1/messages'),
            'kimi': ('openai', 'https://api.moonshot.cn/v1/chat/completions'),
            'zhipu': ('openai', 'https://open.bigmodel.cn/api/paas/v4/chat/completions'),
            'doubao': ('openai', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'),
            'qwen': ('openai', 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'),
            'qianfan': ('openai', 'https://qianfan.baidubce.com/v2/chat/completions'),
            'hunyuan': ('openai', 'https://tokenhub.tencentmaas.com/v1/chat/completions'),
        }
        self.assertEqual(set(ai_providers.PROVIDERS), set(expected))
        for provider_id, provider in ai_providers.PROVIDERS.items():
            protocol, endpoint = expected[provider_id]
            self.assertEqual(provider['protocol'], protocol)
            model = provider['models'][0] if 'models' in provider else {
                'kimi': 'kimi-k3', 'qianfan': 'ernie-5.1', 'hunyuan': 'hy3'
            }.get(provider_id, 'deepseek-flash')
            with self.subTest(provider=provider_id):
                config = {**CONFIG, 'provider': provider_id, 'model': model}
                raw = json.dumps(self.response(protocol, json.dumps(SAMPLE))).encode()
                with patch('ai_providers.safe_request', return_value=(200, 'application/json', raw)) as transport:
                    self.assertEqual(ai_providers.generate_json('test prompt', config), SAMPLE)
                args, kwargs = transport.call_args
                self.assertEqual(args[0], endpoint)
                self.assertNotIn('api.openai.com', args[0]); self.assertNotIn('api.anthropic.com', args[0])
                headers = kwargs['headers']
                self.assertEqual(headers['Authorization'], 'Bearer ' + CONFIG['api_key'])
                self.assertNotIn('x-api-key', headers)
                if protocol == 'anthropic': self.assertEqual(headers['anthropic-version'], '2023-06-01')
                body = json.loads(kwargs['body'])
                expected_fields = {'model', 'messages'}
                if protocol == 'anthropic': expected_fields.add('max_tokens')
                if provider_id == 'deepseek':
                    expected_fields.add('response_format')
                    self.assertEqual(body['response_format'], {'type': 'json_object'})
                self.assertEqual(set(body), expected_fields)
                if protocol == 'anthropic': self.assertEqual(body['max_tokens'], 4096)
                self.assertEqual(body['model'], model); self.assertEqual(body['messages'][0]['content'], 'test prompt')

    def test_both_protocol_error_cases(self):
        for provider_id in ('deepseek', 'minimax'):
            protocol = ai_providers.PROVIDERS[provider_id]['protocol']
            config = {**CONFIG, 'provider': provider_id, 'model': 'MiniMax-M3' if provider_id == 'minimax' else CONFIG['model']}
            cases = [(401, b'{"secret":"must-not-escape"}', 'auth_failed'),
                     (429, b'{}', 'rate_limited'), (500, b'{}', 'service_unavailable'),
                     (200, b'bad JSON', 'bad_response'), (200, b'{}', 'bad_response')]
            for status, raw, code in cases:
                with self.subTest(protocol=protocol, code=code), patch('ai_providers.safe_request', return_value=(status, '', raw)):
                    with self.assertRaises(RequestError) as caught: ai_providers.generate_json('x', config)
                    self.assertEqual(caught.exception.code, code); self.assertNotIn('secret', str(caught.exception))
            for text, reason, code in [('', None, 'empty_response'), ('{}', 'max_tokens' if protocol == 'anthropic' else 'length', 'truncated'), ('{', None, 'invalid_json'), ('[]', None, 'invalid_json')]:
                raw = json.dumps(self.response(protocol, text, reason)).encode()
                with patch('ai_providers.safe_request', return_value=(200, '', raw)):
                    with self.assertRaises(RequestError) as caught: ai_providers.generate_json('x', config)
                    self.assertEqual(caught.exception.code, code)
            with patch('ai_providers.safe_request', side_effect=RequestError('timeout')):
                with self.assertRaisesRegex(RequestError, '超时'): ai_providers.generate_json('x', config)

    def test_balance_and_rejected_parameters_are_not_bad_credentials(self):
        for status, code in [(402, 'insufficient_balance'), (400, 'provider_rejected'), (422, 'provider_rejected')]:
            with self.subTest(status=status), patch('ai_providers.safe_request', return_value=(status, '', b'{"error":{"message":"private upstream details"}}')):
                with self.assertRaises(RequestError) as caught: ai_providers.generate_json('test prompt', CONFIG)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('private', str(caught.exception))

    def test_no_configuration_files_and_no_shared_credentials(self):
        seen = []
        def transport(url, **kwargs):
            seen.append((url, kwargs['headers']['Authorization'], json.loads(kwargs['body'])['model']))
            return 200, '', json.dumps(self.response('openai', '{}')).encode()
        with patch('ai_providers.safe_request', side_effect=transport), patch('pathlib.Path.read_text', side_effect=AssertionError('No config reads')):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda n: ai_providers.generate_json('x', {**CONFIG, 'api_key': f'key-{n}', 'model': f'deepseek-model-{n}'}), (1, 2)))
        self.assertEqual(results, [{}, {}]); self.assertEqual(len(set(seen)), 2)
        self.assertFalse(hasattr(ai_providers, 'load_config')); self.assertFalse(hasattr(ai_providers, 'save_config'))

    def test_config_validation_rejects_foreign_and_custom_endpoints(self):
        for config in [None, {}, {**CONFIG, 'api_key': 'key\r\nX: secret'}, {**CONFIG, 'provider': 'openai'},
                       {**CONFIG, 'provider': 'anthropic'}, {**CONFIG, 'provider': []},
                       {**CONFIG, 'base_url': 'https://api.openai.com/v1'}, {**CONFIG, 'protocol': 'anthropic'},
                       {**CONFIG, 'model': 'kimi-k3'}, {**CONFIG, 'model': '../deepseek-model'},
                       {**CONFIG, 'model': 'deepseek-embedding'}, {**CONFIG, 'model': []}]:
            with self.subTest(config=config), self.assertRaises(RequestError): ai_providers.validate_config(config)

    def test_live_model_list_filters_deduplicates_and_uses_only_selected_target(self):
        for provider_id, expected in [('deepseek', 'deepseek-flash'), ('kimi', 'kimi-k3')]:
            rows = [{'id': expected}, {'id': expected}, {'id': expected + '-audio'},
                    {'id': 'gpt-foreign'}, {'id': expected + '-image', 'output_modalities': ['image']}]
            with patch('ai_providers.safe_request', return_value=(200, '', json.dumps({'data': rows}).encode())) as transport:
                result = ai_providers.list_models(provider_id, 'key-only-this-request')
            self.assertEqual(result['models'], [expected]); self.assertEqual(result['source'], 'live')
            self.assertEqual(transport.call_args.args[0], ai_providers.PROVIDERS[provider_id]['base_url'] + '/models')
            self.assertNotIn('body', transport.call_args.kwargs)
            self.assertEqual(transport.call_args.kwargs['headers'], {'Authorization': 'Bearer key-only-this-request'})

    def test_qianfan_and_hunyuan_model_lists_filter_to_online_first_party_text_models(self):
        cases = [
            ('qianfan', [
                {'id': 'ernie-5.1', 'owned_by': 'Baidu', 'type': 'chat', 'endpoints': ['/v2/chat/completions']},
                {'id': 'ernie-5.0', 'owned_by': 'Baidu', 'type': 'multimodal',
                 'architecture': {'output_modalities': ['text']}, 'endpoints': ['/v2/chat/completions']},
                {'id': 'ernie-image', 'owned_by': 'Baidu', 'type': 'text2image', 'endpoints': ['/v2/images']},
                {'id': 'deepseek-v4', 'owned_by': 'DeepSeek', 'type': 'chat', 'endpoints': ['/v2/chat/completions']},
            ], ['ernie-5.1', 'ernie-5.0'], 'https://qianfan.baidubce.com/v2/models'),
            ('hunyuan', [
                {'id': 'hy3', 'status': 'online'}, {'id': 'hy4', 'status': 'offline'},
                {'id': 'hunyuan-role-latest', 'status': 'online'},
                {'id': 'hy-image-v3', 'status': 'online'}, {'id': 'qwen3.5-plus', 'status': 'online'},
            ], ['hy3', 'hunyuan-role-latest'], 'https://tokenhub.tencentmaas.com/v1/models'),
        ]
        for provider, rows, expected, endpoint in cases:
            with self.subTest(provider=provider), patch('ai_providers.safe_request', return_value=(200, '', json.dumps({'data': rows}).encode())) as transport:
                result = ai_providers.list_models(provider, 'key')
            self.assertEqual(result['models'], expected)
            self.assertEqual(result['source'], 'live')
            self.assertEqual(transport.call_args.args[0], endpoint)

    def test_qwen_catalog_models_use_real_fixed_generation_endpoint(self):
        provider = ai_providers.PROVIDERS['qwen']
        self.assertEqual(provider['protocol'], 'openai')
        self.assertIn('qwen3.8-max', provider['models'])
        with patch('ai_providers.safe_request', return_value=(200, '', json.dumps(
                self.response('openai', json.dumps(SAMPLE))).encode())) as transport:
            self.assertEqual(ai_providers.generate_json('test', {
                'provider': 'qwen', 'api_key': 'test-key', 'model': 'qwen3.8-max'
            }), SAMPLE)
        self.assertEqual(transport.call_args.args[0], 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')

    def test_model_list_errors_are_fixed_and_no_fake_fallback(self):
        cases = [(401, b'{"secret":"hidden"}', 'auth_failed'), (429, b'', 'rate_limited'),
                 (200, b'{', 'bad_response'), (200, b'{"data":{}}', 'bad_response'),
                 (200, b'{"data":[{}]}', 'bad_response'),
                 (200, b'{"data":[{"id":"deepseek-flash","output_modalities":"text"}]}', 'bad_response'),
                 (200, b'{"data":[]}', 'no_models')]
        for status, raw, code in cases:
            with self.subTest(code=code), patch('ai_providers.safe_request', return_value=(status, '', raw)):
                with self.assertRaises(RequestError) as caught: ai_providers.list_models('deepseek', 'test-key')
                self.assertEqual(caught.exception.code, code); self.assertNotIn('hidden', str(caught.exception))
        with patch('ai_providers.safe_request', side_effect=RequestError('timeout')):
            with self.assertRaisesRegex(RequestError, '超时'): ai_providers.list_models('kimi', 'test-key')

    def test_catalog_explicitly_does_not_verify_key_or_account_access(self):
        with patch('ai_providers.safe_request', side_effect=AssertionError('No inference or paid key probe')):
            for provider_id in ('minimax', 'zhipu', 'doubao', 'qwen'):
                result = ai_providers.list_models(provider_id, 'not-a-real-key')
                self.assertEqual(result['source'], 'catalog'); self.assertTrue(result['models'])
                self.assertEqual(set(result), {'models', 'source', 'updated'})
                self.assertEqual(result['updated'], '2026-10-21')
                self.assertNotIn('not-a-real-key', json.dumps(result))
                for model in result['models']:
                    self.assertEqual(ai_providers.validate_config({'provider':provider_id,'api_key':'key','model':model})['model'], model)
                with self.assertRaises(RequestError): ai_providers.validate_config({'provider':provider_id,'api_key':'key','model':'wrong-provider-model'})


class TransportTests(unittest.TestCase):
    def test_urls(self):
        for url in ['http://example.com', 'file:///etc/passwd', 'https://user:key@example.com', 'https://example.com:8080',
                    'https://example.com/#fragment', 'https://example.com/\r\nx', 'https://example.com\\@127.0.0.1', None]:
            with self.subTest(url=url), self.assertRaises(RequestError): safe_http.parse_https_url(url)

    def test_private_and_mixed_dns_blocked(self):
        for ip in ['127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.0.1', '169.254.169.254', '100.100.100.200',
                   '0.0.0.0', '224.0.0.1', '::1', 'fc00::1', 'fe80::1', '::ffff:8.8.8.8', '2002:0808:0808::1']:
            self.assertFalse(safe_http.public_ip(ip), ip)
        self.assertTrue(safe_http.public_ip('8.8.8.8'))
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443)), (2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(RequestError) as caught: safe_http.resolve_public('test.example', 1)
            self.assertEqual(caught.exception.code, 'unsafe_target')
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('169.254.169.254', 443))]), patch('socket.create_connection') as connect:
            with self.assertRaises(RequestError): safe_http.safe_request('https://metadata.test/')
            connect.assert_not_called()

    def test_actual_peer_and_tls_hostname(self):
        raw = MagicMock(); raw.getpeername.return_value = ('8.8.8.8', 443)
        connection = safe_http.PinnedHTTPSConnection('api.example.com', '8.8.8.8', 1)
        connection._context = MagicMock()
        with patch('socket.create_connection', return_value=raw) as connect:
            connection.connect()
            connect.assert_called_once_with(('8.8.8.8', 443), timeout=1)
            connection._context.wrap_socket.assert_called_once_with(raw, server_hostname='api.example.com')
        raw.getpeername.return_value = ('127.0.0.1', 443)
        with patch('socket.create_connection', return_value=raw), self.assertRaises(RequestError): connection.connect()

    def test_redirect_size_and_timeout(self):
        response = MagicMock(); response.status = 302
        response.getheader.side_effect = lambda name, default=None: default
        connection = MagicMock(); connection.getresponse.return_value = response
        with patch('safe_http.resolve_public', return_value='8.8.8.8'), patch('safe_http.PinnedHTTPSConnection', return_value=connection):
            with self.assertRaises(RequestError) as caught: safe_http.safe_request('https://example.com', headers={'Authorization': 'test-key'})
            self.assertEqual(caught.exception.code, 'unsafe_target'); self.assertEqual(connection.request.call_count, 1)
            response.status = 200; response.getheader.side_effect = lambda name, default=None: '999' if name == 'Content-Length' else default
            with self.assertRaises(RequestError) as caught: safe_http.safe_request('https://example.com', max_bytes=10)
            self.assertEqual(caught.exception.code, 'too_large')
            connection.getresponse.side_effect = socket.timeout()
            with self.assertRaises(RequestError) as caught: safe_http.safe_request('https://example.com')
            self.assertEqual(caught.exception.code, 'timeout'); self.assertTrue(connection.close.called)


class ContentTests(unittest.TestCase):
    def test_model_format_repair_is_bounded_and_preserves_text(self):
        malformed = copy.deepcopy(SAMPLE)
        malformed['cover_title'] = '标题超过二十四个字时应交给模型重新提炼而不是在服务端直接截断'
        for provider_id in ('deepseek', 'minimax'):
            protocol = ai_providers.PROVIDERS[provider_id]['protocol']
            config = {**CONFIG, 'provider': provider_id, 'model': 'MiniMax-M3' if provider_id == 'minimax' else CONFIG['model']}
            for first in ('not JSON', json.dumps(malformed)):
                calls = []
                def transport(url, **kwargs):
                    calls.append(kwargs)
                    text = first if len(calls) == 1 else json.dumps(SAMPLE)
                    return 200, '', json.dumps(ProtocolTests().response(protocol, text)).encode()
                with self.subTest(provider=provider_id, first=first), patch('ai_providers.safe_request', side_effect=transport):
                    result = main.summarize_to_slides('自有测试正文。', config)
                    self.assertEqual(result['cover_title'], SAMPLE['cover_title'])
                    self.assertEqual(len(calls), 2)
                    self.assertLess(calls[1]['timeout'], calls[0]['timeout'])
                    self.assertIn('上次输出', json.loads(calls[1]['body'])['messages'][0]['content'])

    def test_format_correction_cannot_extend_model_deadline(self):
        with patch('main.time.monotonic', side_effect=[100, 100, 161]), patch('ai_providers.generate_json', side_effect=RequestError('invalid_json')) as generate:
            with self.assertRaises(RequestError) as caught: main.summarize_to_slides('测试正文。', CONFIG)
        self.assertEqual(caught.exception.code, 'timeout'); generate.assert_called_once()
        self.assertEqual(generate.call_args.kwargs['timeout'], 60)

    def test_model_optional_fields_and_numeric_image_references(self):
        sample = copy.deepcopy(SAMPLE)
        del sample['cover_subtitle']; del sample['cover_tags']
        sample['cover_image'] = ' 1 '
        sample['slides'][0]['image'] = 'null'
        with patch('ai_providers.generate_json', return_value=sample) as generate, patch('main.normalize_image', return_value=data_url(bitmap())) as fetch:
            result = main.summarize_to_slides('![图片](https://image.example/a.png)', CONFIG)
        generate.assert_called_once(); fetch.assert_called_once()
        self.assertEqual(result['cover_subtitle'], ''); self.assertEqual(result['cover_tags'], [])
        self.assertTrue(result['cover_image'].startswith('data:'))

    def test_invalid_model_format_stops_after_one_correction(self):
        for first, expected in [('not JSON', 'invalid_json'), (json.dumps({'slides': []}), 'invalid_card_data')]:
            raw = json.dumps(ProtocolTests().response('openai', first)).encode()
            with self.subTest(expected=expected), patch('ai_providers.safe_request', return_value=(200, '', raw)) as transport:
                with self.assertRaises(RequestError) as caught: main.summarize_to_slides('测试正文。', CONFIG)
            self.assertEqual(caught.exception.code, expected); self.assertEqual(transport.call_count, 2)
        with patch('ai_providers.safe_request', return_value=(401, '', b'{}')) as transport:
            with self.assertRaises(RequestError) as caught: main.summarize_to_slides('测试正文。', CONFIG)
        self.assertEqual(caught.exception.code, 'auth_failed'); transport.assert_called_once()

    def test_long_point_retries_with_exact_location_and_previous_output(self):
        invalid = copy.deepcopy(SAMPLE)
        invalid['slides'] = [copy.deepcopy(SAMPLE['slides'][0]) for _ in range(5)]
        invalid['slides'][4]['content'] = ['要点' * 26]
        corrected = copy.deepcopy(invalid)
        corrected['slides'][4]['content'] = ['要点' * 20]
        with patch('ai_providers.generate_json', side_effect=[invalid, corrected]) as generate:
            result = main.summarize_to_slides('测试正文。', CONFIG)
        self.assertEqual(result['slides'][4]['content'], corrected['slides'][4]['content'])
        self.assertEqual(generate.call_count, 2)
        retry_prompt = generate.call_args_list[1].args[0]
        self.assertIn('第5页第1条要点为52字', retry_prompt)
        self.assertIn('只修复不合规字段', retry_prompt)
        self.assertIn(json.dumps(invalid, ensure_ascii=False, separators=(',', ':')), retry_prompt)

    def test_sentence_overflow_splits_without_losing_text_or_calling_model_again(self):
        sample = copy.deepcopy(SAMPLE)
        point = '甲' * 27 + '。' + '乙' * 26 + '。'
        sample['slides'][0]['content'] = [point, '   ']
        with patch('ai_providers.generate_json', return_value=sample) as generate:
            result = main.summarize_to_slides('测试正文。', CONFIG)
        self.assertEqual(''.join(result['slides'][0]['content']), point)
        self.assertEqual(len(result['slides'][0]['content']), 2)
        generate.assert_called_once()
        self.assertEqual(sample['slides'][0]['content'], [point, '   '])

    def test_sentence_split_does_not_overfill_page_or_split_code(self):
        for point in ['甲' * 27 + '。' + '乙' * 26 + '。', 'https://example.com/' + 'a' * 60]:
            sample = copy.deepcopy(SAMPLE)
            sample['slides'][0]['content'] = [point, '一', '二', '三', '四']
            with patch('ai_providers.generate_json', return_value=sample) as generate:
                result = main.summarize_to_slides('测试正文。', CONFIG)
            self.assertEqual(result['slides'][0]['content'], sample['slides'][0]['content'])
            self.assertTrue(result['draft_issues'])
            self.assertEqual(generate.call_count, 2)

    def test_all_overflow_fields_repaired_without_changing_valid_text_or_image(self):
        sample = copy.deepcopy(SAMPLE)
        sample['slides'][0]['content'] = ['甲' * 55, '乙' * 60, '不能改写的事实']
        sample['cover_subtitle'] = None
        del sample['cover_tags']
        corrected = copy.deepcopy(SAMPLE)
        corrected['slides'][0]['content'] = ['短一', '短二', '被模型意外改写']
        corrected['cover_title'] = '模型意外改写标题'
        with patch('ai_providers.generate_json', side_effect=[sample, corrected]) as generate:
            result = main.summarize_to_slides('原文不应重复发送SECRETARTICLE', CONFIG)
        self.assertEqual(result['cover_title'], sample['cover_title'])
        self.assertEqual(result['slides'][0]['content'], ['短一', '短二', '不能改写的事实'])
        prompt = generate.call_args_list[1].args[0]
        self.assertIn('第1页第1条要点为55字', prompt)
        self.assertIn('第1页第2条要点为60字', prompt)
        self.assertNotIn('SECRETARTICLE', prompt)

    def test_failed_repair_retains_draft_and_strict_render_validation(self):
        sample = copy.deepcopy(SAMPLE)
        sample['slides'][0]['content'] = ['甲' * 55]
        for second in [sample, {}, RequestError('invalid_json'), RequestError('timeout')]:
            with self.subTest(second=type(second).__name__), patch('ai_providers.generate_json', side_effect=[sample, second]):
                result = main.summarize_to_slides('测试正文。', CONFIG)
            self.assertEqual(result['slides'][0]['content'], ['甲' * 55])
            self.assertTrue(result['draft_issues'])
            with self.assertRaises(RequestError):
                main.validate_slides_data(result)

    def test_structural_repair_keeps_article_for_missing_content(self):
        with patch('ai_providers.generate_json', side_effect=[{'slides': []}, SAMPLE]) as generate:
            main.summarize_to_slides('必须保留的原文事实', CONFIG)
        self.assertIn('必须保留的原文事实', generate.call_args_list[1].args[0])

    def test_draft_fallback_does_not_hide_auth_errors(self):
        sample = copy.deepcopy(SAMPLE)
        sample['slides'][0]['content'] = ['甲' * 55]
        with patch('ai_providers.generate_json', side_effect=[sample, RequestError('auth_failed')]):
            with self.assertRaises(RequestError) as caught:
                main.summarize_to_slides('测试正文。', CONFIG)
        self.assertEqual(caught.exception.code, 'auth_failed')

    def test_removed_theme_is_not_a_selectable_or_renderable_style(self):
        self.assertNotIn('ppt-y2k-chrome', main.STYLE_NAMES)
        with self.assertRaises(RequestError):
            main.validate_style('ppt-y2k-chrome')

    def test_regeneration_repairs_fields_without_changing_other_cards_or_images(self):
        sample = copy.deepcopy(SAMPLE); sample['cover_image'] = data_url(bitmap())
        rewritten = {'title': '改写后的标题', 'content': ['保留事实的要点']}
        responses = [json.dumps({'title': '缺少要点'}), json.dumps(rewritten)]
        def transport(url, **kwargs):
            return 200, '', json.dumps(ProtocolTests().response('openai', responses.pop(0))).encode()
        with patch('ai_providers.safe_request', side_effect=transport) as generate:
            result = main.regenerate_slide(sample, 1, CONFIG)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result['slides'][0]['content'], rewritten['content'])
        self.assertEqual(result['cover_image'], sample['cover_image'])
        self.assertEqual(sample['slides'][0]['title'], SAMPLE['slides'][0]['title'])

    def test_images_are_decoded_reencoded_and_bounded(self):
        valid = bitmap()
        self.assertEqual(Image.open(io.BytesIO(main.image_bytes(valid))).size, (80, 50))
        for raw in [b'<svg><script>alert(1)</script></svg>', b'fake png', bitmap(fmt='GIF'), bitmap(fmt='BMP'), b'0' * (main.MAX_IMAGE_BYTES + 1)]:
            with self.subTest(raw=raw[:20]), self.assertRaises(RequestError): main.image_bytes(raw)
        for value in ['data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,!!!!', 'javascript:alert(1)']:
            with self.assertRaises(RequestError): main.data_image(value)
        image = Image.open(io.BytesIO(valid)); output = io.BytesIO()
        image.save(output, 'PNG', pnginfo=__import__('PIL.PngImagePlugin', fromlist=['PngInfo']).PngInfo())
        with patch('main.safe_request', return_value=(200, 'image/png', valid)):
            self.assertTrue(main.normalize_image('https://images.example/pic', __import__('time').monotonic()+2).startswith('data:image/png;base64,'))
        with patch('main.safe_request', return_value=(200, 'image/svg+xml', b'<svg/>')):
            with self.assertRaises(RequestError): main.normalize_image('https://images.example/pic', __import__('time').monotonic()+2)

    def test_shape_text_and_template_injection(self):
        sample = copy.deepcopy(SAMPLE); sample['cover_title'] = '<script>x</script>'
        html = main.render_html(sample, 'apple')
        self.assertIn('&lt;script&gt;x&lt;/script&gt;', html); self.assertNotIn('<script>x</script>', html)
        for style in ['../../config', 'bad', None, [], '__class__']:
            with self.assertRaises(RequestError): main.render_html(SAMPLE, style)
        for mutate in [lambda s: s.update(slides=[]), lambda s: s.update(cover_title='x'*25),
                       lambda s: s['slides'][0].update(content=['x']*6), lambda s: s.update(cover_tags=['x']*6),
                       lambda s: s.update(cover_image='<svg/>'), lambda s: s['slides'][0].update(title={'html': 'bad'})]:
            sample = copy.deepcopy(SAMPLE); mutate(sample)
            with self.assertRaises(RequestError): main.validate_slides_data(sample)

    def test_many_images_use_context_ids_and_only_selected_images_are_fetched(self):
        content = '\n'.join(f'第{i}个主题的正文说明。![主题{i}示意图](https://images.example/{i}.png)' for i in range(1, 21))
        sample = copy.deepcopy(SAMPLE)
        sample['cover_image'] = 18
        sample['slides'][0]['image'] = 3
        def choose(prompt, config, **kwargs):
            self.assertIn('【配图18：主题18示意图】', prompt)
            self.assertIn('第18个主题的正文说明', prompt)
            self.assertIn('最多8张', prompt)
            self.assertIn('1–7个内容页', prompt)
            return sample
        with patch('ai_providers.generate_json', side_effect=choose), patch('main.normalize_image', return_value=data_url(bitmap())) as fetch:
            result = main.summarize_to_slides(content, CONFIG)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], ['https://images.example/18.png', 'https://images.example/3.png'])
        self.assertEqual(result['image_summary'], {'candidates': 20, 'selected': 2, 'used': 2, 'failed': 0})
        self.assertTrue(result['cover_image'].startswith('data:image/png'))

    def test_selected_broken_images_are_skipped_without_losing_copy(self):
        for failure in (RequestError('image_fetch_failed'), RequestError('unsafe_target'), RequestError('too_large')):
            sample = copy.deepcopy(SAMPLE); sample['cover_image'] = 1
            with patch('ai_providers.generate_json', return_value=sample), patch('main.normalize_image', side_effect=failure):
                result = main.summarize_to_slides('示例说明。![配图](https://images.example/a.png)', CONFIG)
            self.assertIsNone(result['cover_image']); self.assertEqual(result['cover_title'], SAMPLE['cover_title'])
            self.assertEqual(result['image_summary'], {'candidates': 1, 'selected': 1, 'used': 0, 'failed': 1})

    def test_images_deduplicate_and_unused_candidates_are_not_downloaded(self):
        text, urls = main.extract_images_from_markdown('第一节 ![甲](https://image.example/a.png) 第二节 ![乙](https://image.example/a.png)')
        self.assertEqual(urls, ['https://image.example/a.png'])
        self.assertIn('【配图1：甲】', text); self.assertIn('【配图1：乙】', text)
        with patch('ai_providers.generate_json', return_value=copy.deepcopy(SAMPLE)), patch('main.normalize_image') as fetch:
            result = main.summarize_to_slides('![无关配图](https://image.example/a.png)' * 15, CONFIG)
        fetch.assert_not_called(); self.assertEqual(result['image_summary']['used'], 0)

    def test_selected_private_image_is_skipped_without_connecting(self):
        sample = copy.deepcopy(SAMPLE); sample['cover_image'] = 1
        with patch('ai_providers.generate_json', return_value=sample), patch('socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]), patch('socket.create_connection') as connect:
            result = main.summarize_to_slides('![配图](https://private.example/a.png)', CONFIG)
        connect.assert_not_called(); self.assertIsNone(result['cover_image'])
        self.assertEqual(result['image_summary']['failed'], 1)

    def test_output_stays_within_eight_cards_and_repeated_selection_fetches_once(self):
        sample = copy.deepcopy(SAMPLE); sample['cover_image'] = 1
        sample['slides'] = [dict(title=f'主题{i}', content=['核心观点'], image=1) for i in range(7)]
        with patch('ai_providers.generate_json', return_value=sample), patch('main.normalize_image', return_value=data_url(bitmap())) as fetch:
            result = main.summarize_to_slides('![相关配图](https://image.example/a.png)', CONFIG)
        self.assertEqual(len(result['slides']) + 1, 8); fetch.assert_called_once()
        self.assertEqual(result['image_summary']['used'], 1)
        sample['slides'].append(dict(title='第九张', content=['超量'], image=1))
        with patch('ai_providers.generate_json', return_value=sample), patch('main.normalize_image') as fetch:
            with self.assertRaises(RequestError): main.summarize_to_slides('![配图](https://image.example/a.png)', CONFIG)
        fetch.assert_not_called()

    def test_model_cannot_introduce_urls(self):
        for reference in ['https://127.0.0.1/secret', 'data:image/png;base64,AAA', 1, True, '999999', {'url': 'https://evil.example'}]:
            sample = copy.deepcopy(SAMPLE); sample['cover_image'] = reference
            with patch('ai_providers.generate_json', return_value=sample), patch('main.normalize_image') as fetch:
                result = main.summarize_to_slides('test article', CONFIG)
            self.assertIsNone(result['cover_image']); fetch.assert_not_called()
        sample = copy.deepcopy(SAMPLE); sample['cover_image'] = 1
        with patch('ai_providers.generate_json', return_value=sample), patch('main.normalize_image', return_value=data_url(bitmap())):
            result = main.summarize_to_slides('a ![test](https://image.example/a.png)', CONFIG)
            self.assertTrue(result['cover_image'].startswith('data:image/png;base64,'))

    def test_all_templates_independent(self):
        self.assertEqual(len(main.TEMPLATES), 37)
        self.assertFalse({'ins', 'ppt-minimal-white', 'ppt-editorial-serif', 'ppt-swiss-grid',
                          'ppt-xiaohongshu-white', 'ppt-japanese-minimal', 'notion',
                          'ppt-magazine-bold'} & main.TEMPLATES.keys())
        for style, filename in main.TEMPLATES.items():
            text = (main.ROOT / filename).read_text()
            self.assertNotIn('{% extends', text); self.assertNotIn('{% include', text)
            self.assertNotIn('<script', text.lower()); self.assertNotIn('|safe', text)
            self.assertIn('id="card-1"', main.render_html(SAMPLE, style))


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.db = Path(self.directory.name) / 'metrics.sqlite3'
        service.app.config.update(TESTING=True, METRICS_DB=str(self.db))
        service._rates.clear(); self.client = service.app.test_client()

    def tearDown(self): self.directory.cleanup()

    def post(self, path, data): return self.client.post(path, data=json.dumps(data), content_type='application/json')

    def test_removed_endpoints_and_privacy(self):
        for path in ['/api/ai-config', '/api/ai-models', '/api/ai-test', '/download/slide_1.png', '/download-all', '/generate', '/api/stats']:
            response = self.client.get(path); self.assertIn(response.status_code, (404, 405))
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200); self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        self.assertEqual(self.client.get('/app?style=chinese').status_code, 200)
        self.assertEqual(self.client.get('/app?style=../../config').status_code, 400)
        for style in ('ins', 'ppt-minimal-white', 'ppt-editorial-serif', 'ppt-swiss-grid',
                      'ppt-xiaohongshu-white', 'ppt-japanese-minimal', 'notion',
                      'ppt-magazine-bold'):
            self.assertEqual(self.client.get(f'/app?style={style}').status_code, 400)
        self.assertEqual(self.client.post('/api/events', json={'event': 'sample_view', 'style': 'apple'}, headers={'Origin': 'https://evil.example'}).status_code, 403)

    def test_untrusted_host_header_is_rejected(self):
        self.assertEqual(self.client.get('/', headers={'Host': 'attacker.example'}).status_code, 400)
        self.assertEqual(self.client.get('/', headers={'Host': 'tuka.guage.chat'}).status_code, 200)

    def test_multipart_part_count_is_bounded(self):
        data = {f'field-{index}': 'x' for index in range(4)}
        data['file'] = (io.BytesIO(bitmap()), 'image.png')
        response = self.client.post('/upload-image', data=data)
        self.assertEqual(response.status_code, 413)

    def test_model_discovery_endpoint_is_private_bounded_and_not_generation(self):
        with patch('ai_providers.safe_request', return_value=(200, '', b'{"data":[{"id":"deepseek-flash"}]}')):
            response = self.post('/api/models', {'provider':'deepseek', 'api_key':'test-discovery-key'})
            self.assertEqual(response.status_code, 200); self.assertEqual(response.json['source'], 'live')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertFalse(self.db.exists(), 'Discovery must not increment generation or store credentials')
        for data in [{'provider':'openai','api_key':'key'}, {'provider':'deepseek','api_key':''},
                     {'provider':'deepseek','api_key':'key','base_url':'https://evil.example'}]:
            self.assertEqual(self.post('/api/models', data).status_code, 400)
        with patch('ai_providers.safe_request', side_effect=RequestError('auth_failed')):
            self.assertEqual(self.post('/api/models', {'provider':'deepseek','api_key':'key'}).status_code, 401)
        service._HEAVY.acquire(); service._HEAVY.acquire()
        try:
            self.assertEqual(self.post('/api/models', {'provider':'deepseek','api_key':'key'}).status_code, 503)
        finally:
            service._HEAVY.release(); service._HEAVY.release()

    def test_image_selection_summary_is_separate_from_editable_cards(self):
        sample = copy.deepcopy(SAMPLE)
        summary = {'candidates':20, 'selected':2, 'used':1, 'failed':1}
        sample['image_summary'] = summary
        with patch('main.summarize_to_slides', return_value=sample):
            response = self.post('/preview', {'content':'自有测试内容。'*12, 'config':CONFIG, 'style':'apple'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['image_summary'], summary)
        self.assertNotIn('image_summary', response.json['slides_data'])

    def test_preview_returns_overflow_draft_but_render_rejects_it(self):
        sample = copy.deepcopy(SAMPLE)
        sample['slides'][0]['content'] = ['甲' * 55]
        with patch('ai_providers.generate_json', return_value=sample):
            response = self.post('/preview', {'content':'自有测试内容。'*12, 'config':CONFIG, 'style':'apple'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['slides_data']['slides'][0]['content'], ['甲' * 55])
        self.assertTrue(response.json['draft_issues'])
        self.assertNotIn('draft_issues', response.json['slides_data'])
        with patch('main.capture_slides') as capture:
            rendered = self.post('/render', {'slides_data':response.json['slides_data'], 'style':'apple'})
        self.assertEqual(rendered.status_code, 400)
        capture.assert_not_called()

    def test_generation_outcome_counted_once(self):
        with patch('main.summarize_to_slides', return_value=SAMPLE):
            self.assertEqual(self.post('/preview', {'content': 'a'*50, 'config': CONFIG, 'style': 'apple'}).status_code, 200)
        with patch('main.summarize_to_slides', side_effect=RequestError('auth_failed')):
            response = self.post('/preview', {'content': 'b'*50, 'config': CONFIG, 'style': 'apple'})
            self.assertEqual(response.status_code, 401); self.assertEqual(response.json['code'], 'auth_failed')
        self.client.get('/'); self.client.get('/'); self.client.get('/app')
        with closing(sqlite3.connect(self.db)) as db:
            counts = dict(db.execute('SELECT event,SUM(count) FROM counts GROUP BY event'))
        self.assertEqual(counts, {'generation_start': 2, 'generation_success': 1, 'generation_failure': 1, 'home_visit': 2, 'app_visit': 1})

    def test_concurrent_requests_do_not_share_content_or_config(self):
        barrier = threading.Barrier(2)
        def summarize(content, config):
            barrier.wait(timeout=5)
            result = copy.deepcopy(SAMPLE)
            result['cover_title'] = content[:1] + config['api_key'][-1:]
            return result
        def send(marker):
            with service.app.test_client() as client:
                return client.post('/preview', json={'content': marker * 50, 'style': 'apple',
                    'config': {**CONFIG, 'api_key': 'test-key-' + marker}}).json
        with patch('main.summarize_to_slides', side_effect=summarize), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(send, ('A', 'B')))
        self.assertEqual([r['slides_data']['cover_title'] for r in results], ['AA', 'BB'])

    def test_events_reject_sensitive_fields_and_server_results(self):
        for data in [{'event': 'generation_success', 'style': 'apple'}, {'event': 'download_click', 'style': 'apple', 'api_key': 'secret'},
                     {'event': 'sample_view', 'style': 'https://secret.example'}, {'event': [], 'style': 'apple'},
                     {'event': 'sample_view', 'style': {'content': 'secret'}}]:
            self.assertEqual(self.post('/api/events', data).status_code, 400)
        self.assertEqual(self.post('/api/events', {'event': 'template_select', 'style': 'apple'}).status_code, 204)
        self.assertNotIn(b'secret', self.db.read_bytes())

    def test_errors_limits_and_upload(self):
        for data in [[], None, {'content': 'short', 'style': 'apple', 'config': CONFIG}]:
            self.assertEqual(self.post('/preview', data).status_code, 400)
        self.assertEqual(self.client.post('/render', data='x'*(32*1024*1024+1), content_type='application/json').status_code, 413)
        self.assertEqual(self.post('/upload-image', {'image_data': data_url(bitmap())}).status_code, 200)
        self.assertEqual(self.post('/upload-image', {'image_data': 'data:image/svg+xml;base64,PHN2Zy8+'}).status_code, 400)
        self.assertEqual(self.post('/regenerate-slide', {'slides_data': SAMPLE, 'slide_index': -1, 'style': 'apple', 'config': CONFIG}).status_code, 400)
        self.assertEqual(self.post('/regenerate-slide', {'slides_data': SAMPLE, 'slide_index': True, 'style': 'apple', 'config': CONFIG}).status_code, 400)
        for _ in range(12): response = self.post('/render', {'slides_data': SAMPLE, 'style': 'invalid'})
        self.assertEqual(response.status_code, 429)

    def test_render_gzip_preserves_exact_pngs_and_negotiates_encoding(self):
        raw = bitmap((1242, 1660))
        body = {'slides_data': SAMPLE, 'style': 'apple'}
        with patch('main.capture_slides', new=AsyncMock(return_value=[raw, raw])), patch('ai_providers.generate_json') as model:
            for route in ('/render', '/regenerate-style'):
                with self.subTest(route=route):
                    plain = self.client.post(route, json=body)
                    compressed = self.client.post(route, json=body, headers={'Accept-Encoding':'gzip'})
                    rejected = self.client.post(route, json=body, headers={'Accept-Encoding':'gzip;q=0, identity'})
                    self.assertEqual(compressed.status_code, 200)
                    self.assertEqual(compressed.headers.get('Content-Encoding'), 'gzip')
                    self.assertIn('Accept-Encoding', compressed.headers['Vary'])
                    self.assertLess(len(compressed.data), len(plain.data))
                    self.assertEqual(gzip.decompress(compressed.data), plain.data)
                    self.assertNotIn('Content-Encoding', rejected.headers)
                    self.assertEqual(rejected.json, plain.json)
                    for image in plain.json['images']:
                        self.assertEqual(base64.b64decode(image['data'].split(',', 1)[1]), raw)
            model.assert_not_called()

    def test_large_multipart_stays_in_memory(self):
        request = service.MemoryRequest.from_values(
            method='POST', data={'image': (io.BytesIO(b'x' * 700_000), 'upload.png')})
        try:
            stream = request.files['image'].stream
            self.assertIsInstance(stream, io.BytesIO)
            self.assertEqual(len(stream.read()), 700_000)
        finally:
            request.close()

    def test_zip_keeps_current_bytes_and_rejects_invalid(self):
        raw = bitmap((1242, 1660)); response = self.post('/download-all', {'images': [data_url(raw)]})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), ['card-01.png']); self.assertEqual(archive.read('card-01.png'), raw)
        self.assertEqual(self.post('/download-all', {'images': [data_url(bitmap())]}).status_code, 400)
        self.assertEqual(self.post('/download-all', {'images': []}).status_code, 400)
        response = self.post('/download-all', {'images': [data_url(raw)] * 8})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(len(archive.namelist()), 8)
        self.assertEqual(self.post('/download-all', {'images': [data_url(raw)] * 9}).status_code, 400)

    def test_ninth_card_is_rejected_before_rendering(self):
        sample = copy.deepcopy(SAMPLE)
        sample['slides'] *= 8
        with patch('main.capture_slides') as capture:
            response = self.post('/render', {'slides_data': sample, 'style': 'apple'})
        self.assertEqual(response.status_code, 400)
        capture.assert_not_called()

    def test_concurrency_gate_and_cleanup(self):
        service._RENDER.acquire()
        try:
            response = self.post('/render', {'slides_data': SAMPLE, 'style': 'apple'})
            self.assertEqual(response.status_code, 503)
        finally: service._RENDER.release()
        with patch('main.capture_slides', side_effect=RuntimeError('sensitive upstream content')):
            response = self.post('/render', {'slides_data': SAMPLE, 'style': 'apple'})
            self.assertEqual(response.status_code, 502); self.assertNotIn(b'sensitive', response.data)
        self.assertTrue(service._RENDER.acquire(blocking=False)); service._RENDER.release()
        self.assertTrue(service._HEAVY.acquire(blocking=False)); service._HEAVY.release()


class RenderCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_and_cancellation_close_browser_context(self):
        for error in (RequestError('render_failed'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                manager, playwright, browser, context, page = [MagicMock() for _ in range(5)]
                manager.__aenter__.return_value = playwright
                playwright.chromium.launch = AsyncMock(return_value=browser)
                browser.new_context = AsyncMock(return_value=context)
                browser.close = AsyncMock()
                context.route = AsyncMock()
                context.new_page = AsyncMock(return_value=page)
                context.close = AsyncMock()
                page.set_content = AsyncMock(side_effect=error)
                with patch('main.async_playwright', return_value=manager):
                    with self.assertRaises(type(error)):
                        await main.capture_slides('<html></html>')
                context.close.assert_awaited_once()
                browser.close.assert_awaited_once()


class MetricsTests(unittest.TestCase):
    def test_concurrent_atomic_retention_readonly_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stats.sqlite3'
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: metrics.record(path, 'template_select', 'apple'), range(80)))
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT SUM(count) FROM counts').fetchone()[0], 80)
                self.assertEqual([row[1] for row in db.execute('PRAGMA table_info(counts)')], ['day', 'event', 'style', 'error', 'count'])
                db.execute('INSERT INTO counts VALUES(?,?,?,?,?)', ((metrics.today()-timedelta(days=90)).isoformat(), 'home_visit', '', '', 9))
            metrics.record(path, 'home_visit')
            before = path.read_bytes(); report = metrics.report(path); self.assertEqual(path.read_bytes(), before)
            self.assertIn('苹果极简 80', report); self.assertIn('非人数', report)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT SUM(count) FROM counts').fetchone()[0], 81)
            with self.assertRaises(RequestError): metrics.record(path, 'unknown')


if __name__ == '__main__': unittest.main()
