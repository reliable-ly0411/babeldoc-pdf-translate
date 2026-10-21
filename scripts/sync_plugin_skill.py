"""Keep the installable nested skill byte-identical to the standalone sources."""
from pathlib import Path
import argparse
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
FILES = ['SKILL.md', 'requirements.txt', 'scripts/pdf_translate.py', 'scripts/repair_runtime.py',
         'scripts/chat_bridge.py', 'scripts/native_context.py', 'scripts/dsh_chat.mjs', 'scripts/windows_job.py', 'scripts/visual_review.py',
         'scripts/model_endpoints.py','scripts/vision_backends.py','scripts/pdf_pipeline.py','scripts/semantic_pipeline.py','scripts/final_audit.py',
         'scripts/audit_receipts.py','scripts/semantic_gate.py','scripts/semantic_mapping.py','scripts/semantic_unit_protocol.py',
         'scripts/pdf_objects.py','scripts/engine_source_map.py','scripts/semantic_objects.py','scripts/native_capture.py','scripts/semantic_filesystem.py',
         'scripts/clipping_relations.py','scripts/prose_ink.py','scripts/render_lineage.py','scripts/source_fragments.py','scripts/source_redaction.py','scripts/gap_rerender.py','scripts/date_literals.py','scripts/numeric_literals.py',
         'scripts/repair_objects.py','scripts/expression_syntax.py','scripts/quantity_roles.py','scripts/translation_contract.py','scripts/semantic_quality.py','scripts/semantic_relations.py','scripts/semantic_relation_spans.py','scripts/semantic_blind.py','scripts/source_repair.py','scripts/region_review.py','scripts/math_operators.py','scripts/prose_completeness.py','scripts/semantic_review.py','scripts/translation_corrections.py']
DIRS = ['references', 'assets', 'agents', 'patches']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    manifests = [json.loads((ROOT / path).read_text(encoding='utf-8'))
                 for path in ('plugin.json', '.codex-plugin/plugin.json')]
    for field in ('name', 'version'):
        if manifests[0][field] != manifests[1][field]:
            raise SystemExit(f'Plugin manifests disagree on {field}')
    destination = ROOT / 'skills' / 'babeldoc-pdf-translate'
    paths = [ROOT / f for f in FILES]
    paths += [f for d in DIRS for f in (ROOT/d).rglob('*') if f.is_file()]
    for source in paths:
        target = destination / source.relative_to(ROOT)
        if args.check:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise SystemExit(f'Out of sync: {target.relative_to(ROOT)}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    print(f'{len(paths)} skill resources verified' if args.check else f'{len(paths)} skill resources synchronized')

if __name__ == '__main__':
    main()
