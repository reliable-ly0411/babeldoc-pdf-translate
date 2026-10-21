"""Diagnose PDF reflow with exact source text, without a translation model.

The result is deliberately untranslated and is never a translation deliverable.
Only BabelDOC's recognized batch and single-paragraph protocols are accepted.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from chat_bridge import checked_request, translation_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--pages', default='3')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--record-sources', action='store_true', help='Opt-in document-text capture; never native prompts or auth data')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    stats = {'kind': 'source-text passthrough; no live inference', 'requests': 0,
             'batch_requests': 0, 'single_requests': 0, 'errors': 0}
    sources = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            status = 200
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.path != '/v1/chat/completions' or not 0 < size <= 512 * 1024:
                    raise ValueError('unsupported request')
                request = checked_request(json.loads(self.rfile.read(size)))
                batch = translation_batch(request)
                if batch is not None:
                    content = json.dumps([{'id': row['id'], 'output': row['input']} for row in batch[2]], ensure_ascii=False)
                    if args.record_sources:
                        sources.extend(row['input'] for row in batch[2])
                    stats['batch_requests'] += 1
                else:
                    prompt = request['messages'][-1]['content']
                    if 'Now translate the following text:\n\n' in prompt and '## Rules' in prompt:
                        content = prompt.rsplit('Now translate the following text:\n\n', 1)[1]
                    elif prompt.startswith(';; Treat next line as plain text input and translate it into ') and 'Input:\n\n' in prompt:
                        content = prompt.split('Input:\n\n', 1)[1]
                    else:
                        raise ValueError('unrecognized single-paragraph protocol')
                    stats['single_requests'] += 1
                    if args.record_sources:
                        sources.append(content)
                stats['requests'] += 1
                response = {'id': 'source-passthrough', 'object': 'chat.completion',
                            'model': 'source-passthrough', 'choices': [{'index': 0, 'finish_reason': 'stop',
                            'message': {'role': 'assistant', 'content': content}}]}
            except (ValueError, KeyError, TypeError):
                stats['errors'] += 1
                status, response = 400, {'error': {'message': 'unrecognized diagnostic request'}}
            data = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        argv = [args.engine, '--files', str(args.input.resolve()), '--output', str(args.output.resolve()),
                '--openai', '--openai-base-url', f'http://127.0.0.1:{server.server_port}/v1',
                '--openai-api-key', 'source-passthrough-public-fixture', '--openai-model', 'source-passthrough',
                '--lang-in', 'en', '--lang-out', 'zh-CN', '--pages', args.pages,
                '--only-include-translated-page', '--no-auto-extract-glossary', '--ignore-cache',
                '--translate-table-text', '--min-text-length', '4', '--watermark-output-mode', 'no_watermark']
        if args.debug:
            argv.append('--debug')
        env = os.environ.copy()
        env['NO_PROXY'] = env['no_proxy'] = '127.0.0.1,localhost,::1'
        with (args.output / 'engine.txt').open('w') as log:
            result = subprocess.run(argv, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        stats['returncode'] = result.returncode
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        (args.output / 'diagnostic.json').write_text(json.dumps(stats, indent=2) + '\n')
        if args.record_sources:
            (args.output / 'document-sources.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(stats))
    return 0 if stats.get('returncode') == 0 and stats['requests'] and not stats['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
