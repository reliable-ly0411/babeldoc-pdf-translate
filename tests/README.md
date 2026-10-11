# Reproducing the checks

Use Python 3.12 and a dedicated virtual environment. From the repository root:

```sh
python -m pip install -r requirements.txt
python scripts/repair_runtime.py --apply
python scripts/repair_runtime.py --check
python -m unittest discover -s tests -v
python scripts/sync_plugin_skill.py --check
```

The unit suite includes the real upstream argument parser, actual PyMuPDF
validation, patched renderer/typesetter and rollback/failure handling. Tests
require the compatibility patch; they must fail on an unpatched runtime.
CI runs this suite on Ubuntu/Python 3.12, then rolls back and reapplies the patch.

For full PDF regression, install ReportLab/Pillow as test-only dependencies and
prepare the engine's font/model assets (warmup may download upstream assets):

```sh
python -m pip install 'reportlab>=4,<5' Pillow
babeldoc --warmup
python tests/create_fixtures.py /tmp/pdf-fixtures
python tests/run_pdf_regression.py /tmp/pdf-fixtures /tmp/pdf-regression --engine /absolute/path/to/babeldoc
```

Each run needs a new output directory. This starts a temporary loopback HTTP
server, replays reviewed translations of the synthetic fixture, executes the
real BabelDOC CLI, and closes the server. Unknown text fails the run. It needs
no provider credentials and makes no live model inference calls. The fixture
translations came from the 2026-10-11 Codex/DSH chat experiments, with short
table labels reviewed in the repair session. The mapping contains only public
synthetic test text, no chat system prompts or account data.

Seven cases cover mono/dual, three watermark settings, both dual layouts and
orders, first/later/noncontiguous selected pages, retained pages and splitting.
Checks include artifact names/counts, physical pages/sizes, watermark presence,
retained-page order, precise identifiers, signed decimal lines, translated
table cells and short-unit font sizes. JSON reports, execution manifests and
PDFs stay in the specified output directory, outside Git.

Use `--case table-numbers` (repeatable) for a targeted rerun. Independently run
Poppler `pdftotext` and render PDFs with `pdftoppm` for visual review. The test
suite does not prove translation accuracy for arbitrary documents, full OCR,
or compatibility with every desktop platform or PDF producer.
