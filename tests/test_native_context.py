"""Identity/status regressions use fixtures, not credentials or live inference."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import chat_bridge as bridge
import native_context as nc
import pdf_translate


class NativeContextTests(unittest.TestCase):
    def context(self, match=True):
        return {'inherited_username_matches_identity': match,
                'effective_identity': 'HOST\\Owner' if match else 'HOST\\CodexSandboxOffline'}

    def test_os_identity_is_not_inherited_username(self):
        with patch.object(nc.os, 'name', 'nt'), patch.object(nc, 'effective_identity', return_value='HOST\\CodexSandboxOffline'):
            report = nc.execution_context('selected.cmd', {'USERNAME': 'Owner', 'USERPROFILE': 'C:/Users/Owner'})
        self.assertFalse(report['inherited_username_matches_identity'])
        self.assertEqual(report['effective_identity'], 'HOST\\CodexSandboxOffline')
        self.assertEqual(report['selected_cli'], 'selected.cmd')

    def test_matching_account_is_case_insensitive(self):
        with patch.object(nc.os, 'name', 'nt'), patch.object(nc, 'effective_identity', return_value='HOST\\OWNER'):
            report = nc.execution_context('selected.cmd', {'USERNAME': 'Owner'})
        self.assertTrue(report['inherited_username_matches_identity'])

    def test_unknown_identity_is_not_invented_from_environment(self):
        with patch.object(nc.os, 'name', 'nt'), patch.object(nc, 'effective_identity', return_value=None):
            report = nc.execution_context('selected.cmd', {'USERNAME': 'Owner'})
        self.assertIsNone(report['effective_identity'])
        self.assertIsNone(report['inherited_username_matches_identity'])

    def test_home_override_report_does_not_read_files_or_mutate_environment(self):
        values = {'USERNAME': 'Owner', 'USERPROFILE': 'C:/Users/Owner', 'CODEX_HOME': 'D:/selected-codex'}
        before = dict(values)
        with patch.object(nc, 'effective_identity', return_value='HOST\\Owner'), patch('builtins.open', side_effect=AssertionError('No credential reads')):
            report = nc.execution_context('selected.cmd', values)
        self.assertEqual(values, before)
        self.assertEqual(report['codex_home_override'], values['CODEX_HOME'])
        self.assertFalse(report['credential_storage_read'])

    def test_sandbox_status_does_not_request_another_login(self):
        code, detail = nc.login_status_error(1, '', 'Not logged in', self.context(False))
        self.assertEqual(code, 'CODEX_EXECUTION_CONTEXT_MISMATCH')
        self.assertEqual(detail['desktop_web_and_cloud_login'], 'not_assessed')
        self.assertFalse(detail['automatic_login_or_credential_migration'])

    def test_matching_or_unknown_context_is_only_locally_unavailable(self):
        for match in (True, None):
            with self.subTest(match=match):
                code, detail = nc.login_status_error(1, 'Not logged in\n', '', self.context(match))
                self.assertEqual(code, 'CODEX_AUTH_UNAVAILABLE_IN_CONTEXT')
                self.assertEqual(detail['scope'], 'selected_cli_and_process_identity_only')

    def test_api_key_status_is_method_mismatch_with_no_fallback(self):
        code, detail = nc.login_status_error(0, 'Logged in using an API key', '', self.context())
        self.assertEqual(code, 'CODEX_AUTH_METHOD_MISMATCH')
        self.assertFalse(detail['automatic_login_or_credential_migration'])

    def test_transport_error_is_not_relabelled_as_sign_in_required(self):
        secret = 'private transport/account detail'
        code, detail = nc.login_status_error(2, '', secret, self.context(False))
        self.assertEqual(code, 'CODEX_LOGIN_STATUS_FAILED')
        self.assertNotIn(secret, json.dumps(detail))
        self.assertFalse(detail['raw_status_output_retained'])

    def test_unknown_success_fails_closed(self):
        code, _ = nc.login_status_error(0, 'unrecognized account status', '', self.context())
        self.assertEqual(code, 'CODEX_LOGIN_STATUS_UNRECOGNIZED')

    def test_success_requires_zero_exit_and_official_status_line(self):
        self.assertIsNone(nc.login_status_error(0, '', '\x1b[32mLogged in using ChatGPT\x1b[0m\n', self.context(False)))
        self.assertEqual(nc.login_status_error(1, 'Logged in using ChatGPT', '', self.context())[0], 'CODEX_LOGIN_STATUS_FAILED')
        self.assertEqual(nc.login_status_error(0, 'example: Logged in using ChatGPT', '', self.context())[0], 'CODEX_LOGIN_STATUS_UNRECOGNIZED')

    def test_doctor_reports_successful_execution_context_without_login_mutation(self):
        client = bridge.NativeClient({'type': 'codex', 'timeout_seconds': 5}, threading.Event())
        results = [subprocess.CompletedProcess([], 0, '', 'Logged in using ChatGPT'),
                   subprocess.CompletedProcess([], 0, 'codex-cli fixture', '')]
        with patch.object(bridge, 'executable', return_value='selected.cmd'), patch.object(nc, 'execution_context', return_value=self.context()), patch.object(client, 'invoke', side_effect=results) as invoke:
            report = client.doctor()
        self.assertTrue(report['ready'])
        self.assertEqual(report['execution_context'], self.context())
        self.assertEqual(report['authentication_method'], 'chatgpt')
        self.assertEqual([x.args[0] for x in invoke.call_args_list], [['selected.cmd', 'login', 'status'], ['selected.cmd', '--version']])
        self.assertEqual(client.inference_calls, 0)

    def test_doctor_failure_stops_after_one_read_only_probe(self):
        client = bridge.NativeClient({'type': 'codex', 'timeout_seconds': 5}, threading.Event())
        status = subprocess.CompletedProcess([], 1, '', 'Not logged in')
        with patch.object(bridge, 'executable', return_value='selected.cmd'), patch.object(nc, 'execution_context', return_value=self.context(False)), patch.object(client, 'invoke', return_value=status) as invoke:
            with self.assertRaises(bridge.BridgeError) as caught:
                client.doctor()
        self.assertEqual(caught.exception.code, 'CODEX_EXECUTION_CONTEXT_MISMATCH')
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(client.inference_calls, 0)

    def test_chat_doctor_cli_preserves_structured_nonsecret_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder) / 'job.json'
            job.write_text(json.dumps({'provider': {'type': 'codex'}}), encoding='utf-8')
            output = io.StringIO()
            error = bridge.BridgeError('CODEX_EXECUTION_CONTEXT_MISMATCH', {'scope': 'selected_cli_and_process_identity_only'})
            with patch.object(sys, 'argv', ['pdf_translate.py', 'chat-doctor', str(job)]), patch.object(pdf_translate.NativeClient, 'doctor', side_effect=error), contextlib.redirect_stdout(output):
                code = pdf_translate.main()
            result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['error'], error.code)
        self.assertEqual(result['detail']['scope'], 'selected_cli_and_process_identity_only')


if __name__ == '__main__':
    unittest.main()
