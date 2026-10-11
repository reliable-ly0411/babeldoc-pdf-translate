"""Opt-in live interruption/recovery experiment. Uses the supplied job's native account.

Run only with explicit model-usage authorization. The supplied PDF should be the
three-page technical fixture and generate at least three translation requests.
No credentials or request prompts are written to the report.
"""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--execute', action='store_true', help='Required: spends the selected native account usage')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required for a live model experiment')
    source_job = args.job.resolve()
    job = json.loads(source_job.read_text())
    if job.get('provider', {}).get('type') not in ('codex', 'dsh'):
        parser.error('This experiment requires a native provider')
    # Relocate the job without changing the original document/glossary/prompt paths.
    for key in ('input', 'prompt_file'):
        if key in job:
            job[key] = str((source_job.parent / Path(job[key]).expanduser()).resolve())
    job['glossaries'] = [str((source_job.parent / Path(p).expanduser()).resolve()) for p in job.get('glossaries', [])]
    if 'dsh_package' in job['provider']:
        job['provider']['dsh_package'] = str((source_job.parent / job['provider']['dsh_package']).resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    cache = output / 'cache'
    job['provider']['cache_dir'] = str(cache)
    interrupted = output / 'interrupted'
    job['output'] = str(interrupted)
    first_job = output / 'interrupted.json'
    first_job.write_text(json.dumps(job, indent=2))
    command = [sys.executable, str(ROOT / 'scripts/pdf_translate.py'), 'run', str(first_job), '--engine', args.engine, '--execute']
    started = time.monotonic()
    with (output / 'interrupted-result.json').open('w') as result, (output / 'interrupted-stderr.txt').open('w') as stderr:
        process = subprocess.Popen(command, stdout=result, stderr=stderr)
        try:
            deadline = time.monotonic() + 600
            while process.poll() is None and len(list(cache.glob('*.json'))) < 2:
                if time.monotonic() > deadline:
                    raise RuntimeError('No two native checkpoints within 600 seconds')
                time.sleep(0.05)
            if process.poll() is not None:
                raise RuntimeError('Job ended before interruption could be tested')
            checkpoint_count = len(list(cache.glob('*.json')))
            process.send_signal(signal.SIGTERM)
            returncode = process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
    first = json.loads((interrupted / 'run-manifest.json').read_text())
    if returncode != 130 or first['status'] != 'interrupted-or-failed' or not first['source_unchanged']:
        raise RuntimeError('Interruption did not stop and preserve the source as expected')
    job['output'] = str(output / 'resumed')
    resumed_job = output / 'resumed.json'
    resumed_job.write_text(json.dumps(job, indent=2))
    command[3] = str(resumed_job)
    with (output / 'resumed-result.json').open('w') as result, (output / 'resumed-stderr.txt').open('w') as stderr:
        resumed = subprocess.run(command, stdout=result, stderr=stderr, timeout=job.get('timeout_seconds', 7200) + 120)
    second = json.loads((output / 'resumed/run-manifest.json').read_text())
    passed = resumed.returncode == 0 and second['status'] == 'needs-review' and second['bridge']['cache_hits'] >= 2 and second['bridge']['live_requests'] > 0
    report = {'backend': job['provider']['type'], 'route': job['provider'].get('route'),
        'seconds': round(time.monotonic()-started, 2), 'checkpoints_before_SIGTERM': checkpoint_count,
        'interrupted_returncode': returncode, 'interrupted_status': first['status'],
        'interrupted_bridge': first['bridge'], 'resumed_bridge': second['bridge'],
        'resumed_returncode': resumed.returncode, 'source_unchanged': second['source_unchanged'], 'passed': passed}
    (output / 'recovery-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
