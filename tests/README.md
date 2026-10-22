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

## Native client experiments (explicit opt-in)

The unit suite uses stub clients for bridge protocol, private caching, bounded
retries, batch completeness, code/placeholder preservation and process cleanup.
It does not consume native model usage. DSH's bridge syntax is checked with
`node --check scripts/dsh_chat.mjs` (the live installation uses Node 24).

For a real model experiment, configure a job from the native examples and follow
[unattended translation](../references/unattended.md). Use only an authorized
account and a synthetic/non-sensitive fixture. A run spends that route's quota
or API balance; the DSH API route requires an explicit user choice.

```sh
python scripts/pdf_translate.py chat-doctor /path/to/native-job.json
python scripts/pdf_translate.py run /path/to/native-job.json --engine /path/to/babeldoc --execute
python tests/run_native_recovery.py /path/to/native-job.json /tmp/native-recovery --engine /path/to/babeldoc --execute
```

The recovery experiment creates a fresh private cache, interrupts the adapter
after two successful requests, then resumes into a new output directory. It
checks exit code 130, the interruption manifest, reused checkpoints and new live
calls. Run separately for each backend. Keep JSON reports/PDFs outside Git and
distinguish live calls, cache hits and deterministic replay in every report.

## Nature R1 Linux benchmark

The public sample, exact source identity, page review, runtime/model versions,
sanitized run summaries and reproduction commands are in
[the historical Linux report](../benchmarks/r1-linux-2026-10-14/REPORT.md); later corrections and current limitations are in
[the Windows technical report](../references/windows-stability-review.md).
The fixture tests reproduce complete-JSON row merging, named-slot omissions,
decimal tails after formula markers, and two-dimensional table glyph loss.
They do not call a model. `tests/run_source_passthrough.py` uses the real engine
with source text returned verbatim to separate layout failures from translation
failures. Its PDFs are deliberately untranslated diagnostics. Opt-in
`--record-sources` records document text; keep private inputs outside Git.

`tests/check_r1_output.py` screens the fixed 11-page mono/side-by-side output
for missing Chinese and leaked markup. Page 6 intentionally retains the author
list and affiliations in English. Passing this screen never replaces visual,
numeric, equation, figure-label, or reading-order review.


## Optional external document evidence

The main public source distribution excludes full PDFs, large real-document geometry
extracts and raw native-response archives. Related tests report a skip when the
specific external file is absent; they are not counted as evidence passes.
`BABELDOC_EXTRA_TEST_DATA` may point to an independently verified evidence root
with the original `tests/fixtures/` and `benchmarks/` relative paths. This does
not install credentials or call a model. `BABELDOC_COVERAGE_CORPUS` and
`BABELDOC_SLOT_PILOT` retain their existing opt-in meanings.

PowerShell example for a caller-supplied local evidence folder:

```powershell
$env:BABELDOC_EXTRA_TEST_DATA = $EvidenceRoot
python -m unittest discover -s tests -v
```

Omit that variable for the public-only suite. Keep the two result counts separate.

This experimental branch retains its original R1 benchmark and geometry fixture.
Those historical files are not refreshed acceptance evidence for the current runtime.
