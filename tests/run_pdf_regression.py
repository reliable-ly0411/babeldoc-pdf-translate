"""Real BabelDOC regression with deterministic, reviewed synthetic translations.

No provider credentials or subscription API. This tests the PDF pipeline, not
model quality. Requires installed model/font assets, reportlab and Pillow.
Run create_fixtures.py first; output directory must not already exist.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adapter', ROOT / 'scripts/pdf_translate.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--case', action='append', help='Run selected cases only; repeat to select more')
    args = parser.parse_args()
    fixtures, output = args.fixtures.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    translations = json.loads((ROOT / 'tests/fixtures/translations.json').read_text(encoding='utf-8'))
    requests, unknown = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            status = 200
            try:
                if self.path != '/v1/chat/completions' or self.headers.get('Authorization') != 'Bearer synthetic-fixture-only':
                    raise ValueError('Unsupported request')
                size = int(self.headers['Content-Length'])
                if not 0 < size <= 200_000:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                prompt = payload['messages'][-1]['content']
                inputs = json.loads(prompt.split('## Here is the input:')[-1])
                requests.extend(x['input'] for x in inputs)
                missing = [x['input'] for x in inputs if x['input'] not in translations]
                if missing:
                    unknown.extend(missing)
                    raise ValueError('Unknown fixture text: ' + repr(missing))
                content = json.dumps([{'id': x['id'], 'output': translations[x['input']]} for x in inputs], ensure_ascii=False)
                response = {'id': 'fixture-replay', 'object': 'chat.completion', 'created': int(time.time()),
                            'model': 'fixture-replay', 'choices': [{'index': 0, 'finish_reason': 'stop',
                            'message': {'role': 'assistant', 'content': content}}],
                            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}
            except Exception as exc:
                status, response = 400, {'error': {'message': str(exc)}}
            data = json.dumps(response, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    env.update(PDF_REGRESSION_KEY='synthetic-fixture-only', no_proxy='localhost,127.0.0.1,[::1]')
    base = {'input': str(fixtures / 'technical.pdf'), 'source_language': 'en', 'target_language': 'zh-CN',
            'outputs': 'both', 'watermark': 'both', 'auto_terms': False, 'ignore_cache': True,
            'translate_tables': True, 'qps': 5, 'workers': 2,
            'glossaries': [str(fixtures / 'glossary.csv')],
            'provider': {'base_url': f'http://127.0.0.1:{server.server_port}/v1',
                         'model': 'fixture-replay', 'api_key_env': 'PDF_REGRESSION_KEY'}}
    cases = {
        'single-watermark': {'pages': '1', 'selected_pages_only': True, 'font': 'script'},
        'table-numbers': {'pages': '2', 'selected_pages_only': True, 'font': 'sans-serif'},
        'split-alternating': {'pages': '1,3', 'selected_pages_only': True, 'dual_layout': 'alternating',
                              'translated_first': True, 'max_pages_per_part': 1, 'font': 'serif'},
        'retained-pages': {'pages': '1', 'translated_first': True},
        'retained-late-page': {'pages': '2', 'dual_layout': 'alternating', 'translated_first': False},
        'split-no-watermark': {'pages': '1,3', 'selected_pages_only': True, 'max_pages_per_part': 1,
                              'watermark': 'no_watermark', 'outputs': 'dual'},
        'late-watermarked': {'pages': '2', 'selected_pages_only': True, 'watermark': 'watermarked',
                             'dual_layout': 'alternating', 'outputs': 'dual'},
    }
    if args.case:
        unknown_cases = set(args.case) - cases.keys()
        if unknown_cases:
            parser.error('Unknown cases: ' + ', '.join(sorted(unknown_cases)))
        cases = {name: value for name, value in cases.items() if name in args.case}
    results = []
    try:
        for name, options in cases.items():
            job = {**base, **options, 'output': str(output / name)}
            path = output / f'{name}.json'
            path.write_text(json.dumps(job, indent=2), encoding='utf-8')
            started = time.monotonic()
            with (output / f'{name}.log').open('w', encoding='utf-8') as log:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/pdf_translate.py'), 'run', str(path),
                                         '--engine', args.engine, '--execute'], env=env, stdout=log, stderr=subprocess.STDOUT)
            manifest = json.loads((output / name / 'run-manifest.json').read_text(encoding='utf-8'))
            errors = []
            if result.returncode or manifest['status'] != 'needs-review':
                errors.append('Adapter failed: ' + repr(manifest.get('output_validation')))
            texts = {}
            for pdf in sorted((output / name).glob('*.pdf')):
                with pymupdf.open(pdf) as doc:
                    texts[pdf.name] = ''.join(page.get_text() for page in doc)
                    has_watermark = 'BabelDOC' in texts[pdf.name]
                    if has_watermark == ('.no_watermark.' in pdf.name):
                        errors.append(pdf.name + ': incorrect watermark content')
                    if name == 'retained-late-page':
                        expected_titles = ['Flight Control Experiment', 'Flight Control Experiment',
                                           'Measurements and Parameters', '测量结果与参数',
                                           'Figures and Two Columns', 'Figures and Two Columns'] if '.dual.' in pdf.name else [
                                           'Flight Control Experiment', '测量结果与参数', 'Figures and Two Columns']
                        for page, title in zip(doc, expected_titles):
                            if title not in page.get_text():
                                errors.append(pdf.name + ': incorrect retained page order')
                    if name == 'table-numbers' and '.mono.' in pdf.name:
                        lines = [''.join(span['text'] for span in line['spans']) for page in doc
                                 for block in page.get_text('dict')['blocks'] if block['type'] == 0 for line in block['lines']]
                        if not any('-0.25' in line for line in lines):
                            errors.append(pdf.name + ': signed decimal is split or changed')
                        for word in ('参数', '数值', '单位', '增益', '采样率', '延迟', '电压', '12.5', '100', '0.02'):
                            if word not in texts[pdf.name]:
                                errors.append(pdf.name + ': missing ' + word)
                        units = [span for page in doc for block in page.get_text('dict')['blocks'] if block['type'] == 0
                                 for line in block['lines'] for span in line['spans'] if span['text'].strip() in ('Hz', 's', 'V')]
                        if len(units) != 3 or any(span['size'] < 10 for span in units):
                            errors.append(pdf.name + ': short SI unit font was reduced')
                    if name in ('single-watermark', 'split-alternating') and '.mono.' in pdf.name:
                        if 'CTRL-2026-A' not in texts[pdf.name]:
                            errors.append(pdf.name + ': identifier changed')
            (output / f'{name}-text.json').write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding='utf-8')
            summary = {'case': name, 'returncode': result.returncode, 'seconds': round(time.monotonic()-started, 2),
                       'pdf_count': len(texts), 'errors': errors, 'passed': not errors}
            results.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        report = {'results': results, 'unknown': sorted(set(unknown)), 'requested_texts': sorted(set(requests)),
                  'translation_source': 'Reviewed synthetic fixture replay; no live provider inference'}
        (output / 'regression.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if len(results) == len(cases) and all(x['passed'] for x in results) and not unknown else 1


if __name__ == '__main__':
    raise SystemExit(main())
