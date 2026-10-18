"""Transport/lifecycle tests use a fake native client; these are not live model evidence."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as b
import pdf_translate as adapter

REQUEST = {'messages': [{'role': 'user', 'content': 'Translate voltage into Chinese'}], 'response_format': None}


class FakeClient:
    version = 'fixture-1'
    def __init__(self, replies=None):
        self.replies = list(replies or ['电压'])
        self.calls = 0
    def doctor(self):
        return {'ready': True, 'native_version': self.version}
    def translate(self, request):
        self.calls += 1
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.provider = {'type': 'codex', 'timeout_seconds': 5, 'retries': 0}
    def tearDown(self):
        self.tmp.cleanup()
    def post(self, bridge, body=REQUEST, key=None, path='/chat/completions'):
        opener = build_opener(ProxyHandler({}))
        req = Request(bridge.url + path, data=json.dumps(body).encode(),
                      headers={'Authorization': 'Bearer ' + (bridge.key if key is None else key), 'Content-Type': 'application/json'})
        try:
            with opener.open(req, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_loopback_auth_and_openai_response(self):
        client = FakeClient()
        with b.ChatBridge(self.provider, client) as bridge:
            self.assertEqual(bridge.server.server_address[0], '127.0.0.1')
            self.assertEqual(self.post(bridge, key='wrong')[0], 401)
            self.assertEqual(self.post(bridge, path='/other')[0], 404)
            self.assertFalse(bridge.failed.is_set())
            status, response = self.post(bridge)
            self.assertEqual(status, 200)
            self.assertEqual(response['choices'][0]['message']['content'], '电压')
            self.assertEqual(response['choices'][0]['finish_reason'], 'stop')
            address = bridge.server.server_address
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex(address), 0)
        self.assertEqual(client.calls, 1)

    def test_authenticated_invalid_input_fails_closed(self):
        with b.ChatBridge(self.provider, FakeClient()) as bridge:
            self.assertEqual(self.post(bridge, {'messages': [], 'stream': True})[0], 400)
            self.assertTrue(bridge.failed.is_set())
            self.assertEqual(self.post(bridge)[0], 400)
            self.assertEqual(bridge.client.calls, 0)

    def test_shutdown_waits_for_inflight_failure_accounting(self):
        started = threading.Event()
        class WaitingClient(FakeClient):
            def translate(self, request):
                started.set()
                if not bridge.cancel.wait(2):
                    raise RuntimeError('Cancellation did not reach the native client')
                # Model cleanup may finish just after the listener shuts down.
                time.sleep(0.03)
                raise b.BridgeError('CANCELLED')
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with b.ChatBridge(self.provider, WaitingClient()) as bridge:
                pending = pool.submit(self.post, bridge)
                self.assertTrue(started.wait(2))
            self.assertEqual(bridge.stats['failed_requests'], 1)
            self.assertEqual(bridge.stats['errors'], ['CANCELLED'])
            self.assertEqual(pending.result(timeout=2)[0], 400)

    def test_empty_invalid_json_and_native_failure_are_not_success(self):
        cases = [('', REQUEST, 'INVALID_RESPONSE'),
                 ('```json\n{}\n```', {**REQUEST, 'response_format': {'type': 'json_object'}}, 'INVALID_JSON_RESPONSE'),
                 (b.BridgeError('ACCOUNT_QUOTA'), REQUEST, 'ACCOUNT_QUOTA')]
        for reply, request, code in cases:
            with self.subTest(code=code), b.ChatBridge(self.provider, FakeClient([reply])) as bridge:
                status, response = self.post(bridge, request)
                self.assertEqual(status, 400)
                self.assertEqual(response['error']['code'], code)
                self.assertTrue(bridge.failed.is_set())
                self.assertEqual(bridge.stats['completed_requests'], 0)

    def test_transient_retry_is_bounded_and_auth_is_not_retried(self):
        for code, expected_calls in [('TRANSPORT', 2), ('ACCOUNT_TOKEN_INVALID', 1)]:
            with self.subTest(code=code):
                client = FakeClient([b.BridgeError(code), '电压'])
                with b.ChatBridge({**self.provider, 'retries': 1}, client) as bridge:
                    status, _ = self.post(bridge)
                    self.assertEqual(client.calls, expected_calls)
                    self.assertEqual(status, 200 if code == 'TRANSPORT' else 400)

    def test_retry_exhaustion_and_later_requests_do_not_spend_more(self):
        client = FakeClient([b.BridgeError('SERVER'), b.BridgeError('SERVER')])
        with b.ChatBridge({**self.provider, 'retries': 1}, client) as bridge:
            self.assertEqual(self.post(bridge)[0], 400)
            self.assertEqual(self.post(bridge)[0], 400)
            self.assertEqual(client.calls, 2)

    def test_model_call_budget_stops_new_requests_but_allows_cached_reply(self):
        client = FakeClient(['电压', '电流'])
        with b.ChatBridge({**self.provider, 'max_model_calls': 1}, client) as bridge:
            self.assertEqual(bridge.complete(REQUEST), '电压')
            self.assertEqual(bridge.complete(REQUEST), '电压')
            with self.assertRaisesRegex(b.BridgeError, 'NATIVE_CALL_BUDGET_EXHAUSTED'):
                bridge.complete({'messages': [{'role': 'user', 'content': 'Translate current'}], 'response_format': None})
            self.assertEqual(client.calls, 1)
            self.assertEqual(bridge.stats['cache_hits'], 1)

    def test_model_call_budget_counts_failed_attempts_and_validates_types(self):
        for value in (True, 0, 513, '4'):
            with self.assertRaises(ValueError):
                b.validate_provider({**self.provider, 'max_model_calls': value}, self.base)
        client = FakeClient([b.BridgeError('TRANSPORT'), '电压'])
        with b.ChatBridge({**self.provider, 'retries': 1, 'max_model_calls': 1}, client) as bridge:
            with self.assertRaisesRegex(b.BridgeError, 'NATIVE_CALL_BUDGET_EXHAUSTED'):
                bridge.complete(REQUEST)
            self.assertEqual(client.calls, 1)

    def test_parallel_duplicates_are_serialized_and_deduplicated(self):
        client = FakeClient()
        with b.ChatBridge(self.provider, client) as bridge:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(lambda _: self.post(bridge)[0], range(8)))
            self.assertEqual(results, [200] * 8)
            self.assertEqual(client.calls, 1)
            self.assertEqual(bridge.stats['cache_hits'], 7)

    def test_private_atomic_cache_recovers_in_new_bridge(self):
        self.provider['cache_dir'] = str(self.base / 'cache')
        for live in (True, False):
            client = FakeClient()
            with b.ChatBridge(self.provider, client) as bridge:
                self.assertEqual(self.post(bridge)[0], 200)
                self.assertEqual(client.calls, int(live))
        paths = list((self.base / 'cache').iterdir())
        self.assertEqual(len(paths), 1)
        if os.name == 'posix':
            self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        self.assertNotIn('Translate voltage', paths[0].read_text(encoding='utf-8'))
        # A modified checkpoint cannot silently become translation output.
        data = json.loads(paths[0].read_text(encoding='utf-8'))
        data['content'] = 'tampered'
        paths[0].write_text(json.dumps(data))
        with b.ChatBridge(self.provider, FakeClient()) as bridge:
            self.assertEqual(self.post(bridge)[1]['error']['code'], 'INVALID_CACHE')

    def test_cache_identity_includes_model_and_native_version(self):
        self.provider['cache_dir'] = str(self.base / 'cache')
        for model, version in [('one', 'v1'), ('two', 'v1'), ('two', 'v2')]:
            client = FakeClient()
            client.version = version
            with b.ChatBridge({**self.provider, 'model': model}, client) as bridge:
                self.post(bridge)
                self.assertEqual(client.calls, 1)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission bits')
    def test_public_cache_is_rejected(self):
        path = self.base / 'public'
        path.mkdir(mode=0o755)
        with self.assertRaisesRegex(b.BridgeError, 'CACHE_MUST_BE_PRIVATE'):
            with b.ChatBridge({**self.provider, 'cache_dir': str(path)}, FakeClient()):
                pass

    def test_oversize_and_tool_requests_rejected(self):
        for change in ({'tools': [{'type': 'function'}]}, {'functions': [{}]}, {'n': 2},
                       {'messages': [{'role': 'user', 'content': []}]}, {'response_format': {'type': 'json_schema'}}):
            with self.subTest(change=change), self.assertRaises(b.BridgeError):
                b.checked_request({**REQUEST, **change})
        with self.assertRaisesRegex(b.BridgeError, 'INVALID_RESPONSE'):
            b.checked_content('x' * (b.MAX_REPLY + 1), REQUEST)

    def test_provider_validation_and_relative_cache(self):
        provider = b.validate_provider({'type': 'dsh', 'dsh_package': 'dsh/package.json', 'cache_dir': 'cache'}, self.base)
        self.assertEqual(provider['cache_dir'], str(self.base / 'cache'))
        for change in ({'type': 'unknown'}, {'api_key': 'forbidden'}, {'retries': True}, {'retries': 3}, {'timeout_seconds': 0}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                b.validate_provider({**self.provider, **change}, self.base)

    def test_dsh_route_must_be_explicit_and_never_falls_back(self):
        account = b.validate_provider({'type': 'dsh', 'dsh_package': 'dsh/package.json'}, self.base)
        self.assertEqual(account['route'], 'deepseek-account')
        official = b.validate_provider({**account, 'route': 'deepseek-official'}, self.base)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'opaque-native-value'}):
            self.assertNotIn('DEEPSEEK_API_KEY', b.NativeClient(account, threading.Event()).env)
            self.assertEqual(b.NativeClient(official, threading.Event()).env['DEEPSEEK_API_KEY'], 'opaque-native-value')
        with self.assertRaises(ValueError):
            b.validate_provider({**account, 'route': 'other'}, self.base)

    def test_unexpected_native_exception_still_aborts_engine(self):
        with b.ChatBridge(self.provider, FakeClient([RuntimeError('private prompt')])) as bridge:
            status, response = self.post(bridge)
            self.assertEqual(status, 400)
            self.assertTrue(bridge.failed.is_set())
            self.assertNotIn('private prompt', str(response))

    def test_code_is_hidden_from_model_and_restored_verbatim(self):
        original = 'Configuration example: gain=2.5; sample_rate=100; mode=TEST'
        request = {'messages': [{'role': 'user', 'content': 'Translate:\n## Here is the input:\n' + json.dumps([
            {'id': 1, 'input': original}, {'id': 2, 'input': 'Gain {v1}'}])}], 'response_format': None}
        masked, protected = b.mask_code(request)
        self.assertNotIn('gain=2.5', masked['messages'][0]['content'])
        self.assertIn('gain=2.5', request['messages'][0]['content'])
        rows = b.translation_batch(masked)[2]
        reply = json.dumps([{'id': r['id'], 'output': r['input'].replace('Configuration example', '配置示例').replace('Gain', '增益')} for r in rows])
        restored = b.restore_code(reply, request, protected)
        self.assertIn('gain=2.5; sample_rate=100; mode=TEST', restored)
        b.checked_content(restored, request)
        with self.assertRaisesRegex(b.BridgeError, 'PROTECTED_TEXT_CHANGED'):
            b.checked_content(restored.replace('sample_rate', '采样率'), request)
        with self.assertRaisesRegex(b.BridgeError, 'PROTECTED_TEXT_CHANGED'):
            b.checked_content(restored.replace('{v1}', ''), request)

    def test_missing_duplicate_and_unknown_batch_ids_fail_closed(self):
        request = {'messages': [{'role': 'user', 'content': '## Here is the input:\n' + json.dumps([
            {'id': 1, 'input': 'Voltage'}, {'id': 2, 'input': 'Gain'}])}], 'response_format': None}
        for rows in [[{'id': 1, 'output': '电压'}], [{'id': 1, 'output': '电压'}, {'id': 1, 'output': '增益'}],
                     [{'id': 1, 'output': '电压'}, {'id': 3, 'output': '增益'}], [{'id': 1, 'output': '电压'}, {'id': 2, 'output': ''}]]:
            with self.subTest(rows=rows), self.assertRaisesRegex(b.BridgeError, 'INCOMPLETE_TRANSLATION_BATCH'):
                b.checked_content(json.dumps(rows), request)

    def test_babeldoc_split_identifiers_remain_one_protected_code_fragment(self):
        source = 'Configuration example: gain{v1}.5; sample{v2}rate{v3}; mode{v4}TEST'
        request = {'messages': [{'role': 'user', 'content': 'Translate\n## Here is the input:\n\n' + json.dumps([
            {'id': 3, 'input': source, 'layout_label': 'abandon'}])}], 'response_format': None}
        masked, protected = b.mask_code(request)
        self.assertNotIn('sample', masked['messages'][0]['content'])
        self.assertEqual(len(protected['3']), 1)
        reply = json.dumps([{'id': 3, 'output': b.translation_batch(masked)[2][0]['input'].replace('Configuration example', '配置示例')}])
        restored = b.restore_code(reply, request, protected)
        b.checked_content(restored, request)
        self.assertIn('gain{v1}.5; sample{v2}rate{v3}; mode{v4}TEST', restored)
        with self.assertRaisesRegex(b.BridgeError, 'PROTECTED_TEXT_CHANGED'):
            b.checked_content(restored.replace('sample', '采样'), request)

    def test_native_job_with_zero_requests_is_not_a_translation(self):
        import pymupdf
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=300)
            doc.save(self.base / 'input.pdf')
        path = self.base / 'job.json'
        path.write_text(json.dumps({'input': 'input.pdf', 'output': 'out', 'target_language': 'zh-CN',
                                   'outputs': 'mono', 'provider': {'type': 'codex'}}))
        flags = {x for x in adapter.prepare(path)[3] if x.startswith('--')} | {'--config'}
        def engine(*args, **kwargs):
            with pymupdf.open() as doc:
                doc.new_page(width=200, height=300)
                doc.save(self.base / 'out/input.zh-CN.mono.pdf')
            return subprocess.CompletedProcess([], 0, '', '')
        with patch.object(adapter, 'probe', return_value=(flags, 'fixture')), patch.object(adapter, 'executable', return_value='fixture'), patch.object(adapter, 'ChatBridge', side_effect=lambda provider: b.ChatBridge(provider, FakeClient())), patch.object(adapter, 'run_bounded', side_effect=engine):
            result = adapter.run_job(path, 'fixture', True)
        self.assertTrue(result['output_validation']['valid'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['status'], 'failed')

    def test_timeout_cancellation_and_output_limit(self):
        for kwargs, code, script in [({'timeout': 0.2}, 'TIMEOUT', 'import time;time.sleep(10)'),
            ({'timeout': 5, 'limit': 1000}, 'OUTPUT_LIMIT', 'print("x"*10000)'),
            ({'timeout': 5, 'cancel': self._cancelled()}, 'CANCELLED', 'import time;time.sleep(10)')]:
            start = time.monotonic()
            with self.subTest(code=code), self.assertRaisesRegex(b.BridgeError, code):
                b.run_bounded([sys.executable, '-c', script], '', **kwargs)
            self.assertLess(time.monotonic() - start, 3)

    @staticmethod
    def _cancelled():
        event = threading.Event()
        event.set()
        return event

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups')
    def test_timeout_kills_owned_descendant(self):
        marker = self.base / 'pid'
        child = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'
        script = f'import subprocess,sys,time,pathlib;p=subprocess.Popen([sys.executable,"-c",{child!r}]);pathlib.Path({str(marker)!r}).write_text(str(p.pid));time.sleep(60)'
        with self.assertRaisesRegex(b.BridgeError, 'TIMEOUT'):
            b.run_bounded([sys.executable, '-c', script], '', 0.4)
        pid = int(marker.read_text())
        proc = Path(f'/proc/{pid}/stat')
        # Orphaned descendants may briefly be zombies waiting for init; they are dead.
        deadline = time.monotonic() + 1
        while proc.exists() and proc.read_text().split()[2] != 'Z' and time.monotonic() < deadline:
            time.sleep(0.01)
        if proc.exists():
            self.assertEqual(proc.read_text().split()[2], 'Z')

    def test_native_dsh_errors_redact_raw_stderr_and_do_not_fallback(self):
        client = b.NativeClient({'type': 'dsh', 'dsh_package': '/fixture/package.json', 'model': 'deepseek-flash', 'timeout_seconds': 5}, threading.Event())
        result = subprocess.CompletedProcess([], 1, '{"error":"ACCOUNT_SIGN_IN_REQUIRED"}', 'private-token-and-prompt')
        with patch.object(b, 'executable', return_value='node'), patch.object(client, 'invoke', return_value=result) as invoke:
            with self.assertRaisesRegex(b.BridgeError, '^ACCOUNT_SIGN_IN_REQUIRED$'):
                client.doctor()
            self.assertNotIn('deepseek-official', str(invoke.call_args))

    def test_codex_requires_chatgpt_and_scrubs_api_key_environment(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'private', 'DEEPSEEK_API_KEY': 'private'}):
            client = b.NativeClient(self.provider, threading.Event())
        self.assertNotIn('OPENAI_API_KEY', client.env)
        self.assertNotIn('DEEPSEEK_API_KEY', client.env)
        result = subprocess.CompletedProcess([], 0, 'Logged in using an API key', '')
        with patch.object(b, 'executable', return_value='codex'), patch.object(client, 'invoke', return_value=result):
            with self.assertRaisesRegex(b.BridgeError, 'CODEX_AUTH_METHOD_MISMATCH'):
                client.doctor()

    def test_codex_rejects_missing_completion_empty_output_and_tool_use(self):
        cases = [('thread.started', None, 'INCOMPLETE_TURN'),
                 ('turn.completed', {'type': 'command_execution'}, 'UNEXPECTED_TOOL_USE'),
                 ('turn.completed', None, 'NATIVE_PROTOCOL_ERROR')]
        for event_type, item, code in cases:
            client = b.NativeClient(self.provider, threading.Event())
            events = [{'type': event_type}]
            if item:
                events.append({'type': 'item.completed', 'item': item})
            result = subprocess.CompletedProcess([], 0, '\n'.join(map(json.dumps, events)), '')
            with self.subTest(code=code), patch.object(b, 'executable', return_value='codex'), patch.object(client, 'invoke', return_value=result):
                with self.assertRaisesRegex(b.BridgeError, code):
                    client.translate(REQUEST)

    def test_job_native_plan_forces_serial_and_engine_cache_bypass(self):
        (self.base / 'input.pdf').write_bytes(b'prepare only')
        job = {'input': 'input.pdf', 'output': 'out', 'target_language': 'zh-CN', 'provider': {'type': 'codex'}}
        path = self.base / 'job.json'
        path.write_text(json.dumps(job))
        normalized, _, _, args = adapter.prepare(path)
        self.assertIn('--ignore-cache', args)
        self.assertEqual(normalized['workers'], 1)
        job['workers'] = 2
        path.write_text(json.dumps(job))
        with self.assertRaisesRegex(ValueError, 'require workers=1'):
            adapter.prepare(path)


if __name__ == '__main__':
    unittest.main()
