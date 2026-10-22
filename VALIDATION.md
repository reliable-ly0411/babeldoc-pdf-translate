# Validation status: 1.5.0-rc.28

This is a bounded Windows/R1 prerelease, not a stable release or validation of arbitrary PDFs. The release source is merge commit `fba043bdc6a6d33bc889ac1459171dd18876821f`; documentation may advance independently without changing that release.

| Check | Recorded result |
| --- | --- |
| Windows offline suite | 624 tests: 622 passed, 2 existing platform skips |
| Linux merged-source CI | 624 tests: 594 passed, 30 skips (29 unavailable real-document evidence checks, 1 Windows-only check) |
| Independent rc.28 review | 14 offline tests passed; 15 configuration comparisons agreed; 271 release files matched the fixed source |
| Runtime and skill packaging | Six-file patch installation/migration/rollback/reapply/idempotence checks passed; 83 skill mirrors matched |
| R1 recovered full-paper cache renders | Two runs, each 66 cache hits, zero new calls/failures; all 11 pages matched in text, size and 144 dpi pixels |

These results are separate checks, not an aggregate quality score. Skipped evidence is not a passed check. The R1 PDFs were generated with the rc.26 layout correction; rc.27/rc.28 do not change those PDF bytes. Cache recovery/repeatability does not establish a successful full-paper empty-cache translation.

## Remaining limits

- R1 page 3 formula overlap is fixed. English preservation/coverage, terminology, footer association and minor line wrapping remain disclosed limitations.
- PyMuPDF 1.28.2 can omit the example equals sign in the bilingual 600 dpi view; 144/300 dpi, the monolingual output and PDFium 600 dpi were checked as normal. Do not claim strict equality for the affected view.
- L1Quad (arXiv:2302.07208) page 5 empty-cache pilot failed after 5 Luna/low calls with `INVALID_TEXT_SLOTS` / `BRIDGE_ABORTED`. No PDF or cache rerun resulted; full-paper acceptance is incomplete. The 21-page source pass-through is an untranslated diagnostic.
- Explicit Codex `max` configuration and mock CLI forwarding pass. Real `max` inference and the full Astra development final audit remain unverified.
- `PROTOCOL_VALIDATED=False` remains in force. Model clear replies, offline tests and retained `best.*` files do not establish automatic delivery acceptance or general repair reliability.

Sources: [rc.28 technical record](https://github.com/reliable-ly0411/babeldoc-pdf-translate/issues/10#issuecomment-6251690944), [merged-source CI](https://github.com/reliable-ly0411/babeldoc-pdf-translate/actions/runs/39142525785), [reproduction instructions](tests/README.md).

The following notes retain earlier results and failures for traceability. Version-specific “draft” or “pending” statements below describe those historical checkpoints, not the current source-publication state.

# Historical validation notes

Current development candidate: **1.5.0-rc.26**. Source publication is separate
from PDF acceptance; this draft does not enable the unvalidated production gate.

The inherited rc.24 full offline run was 609 tests: 607 passed and 2 existing skips,
with zero model calls. The rc.25 context regression adds changed-contract and
preservation-scope checks. Public and optional-external-evidence suite results
are reported on the pull request and CI; skipped evidence is not a passed check.

See [the concise Windows technical report](references/windows-stability-review.md)
for implemented behavior, real-run limits and remaining acceptance. Reproduction
commands and optional fixtures are in [tests/README.md](tests/README.md).
Historical detailed findings remain in [issue10](https://github.com/reliable-ly0411/babeldoc-pdf-translate/issues/10).
Large raw evidence and full PDFs are retained locally rather than shipped here.


Preceding rc.25 public profile: **614 tests, 584 passed, 30 explicitly reported
skips, zero failures/errors, zero real model calls**. The skips include the
unbundled real-document evidence and existing optional/platform checks. Node
syntax, the six-file installed runtime patch and 83 skill mirrors also passed.
The first packaging attempt omitted a test dependency; its failed log is retained
locally, the source dependency was added, and the complete public suite reran.
The optional external-evidence profile also completed: **614 tests, 612 passed,
2 existing Windows/POSIX skips, zero failures/errors and zero real model calls**.
Source hashes were unchanged throughout both successful runs. A separate
external-profile attempt was interrupted by the execution transport; its partial
log is retained and is not counted as a passed run.

At rc.25, an independent all-page review found one remaining PDF release blocker on page 3:
translated prose overlaps the end of an inline formula. This historical blocker was corrected in rc.26; see the current status above.

## 历史复杂论文扩展验收

新一轮公开航空航天与 AI 论文的原文、作业、提示词、参考输出和原生用量见 [实验报告](benchmarks/papers-2026-10/REPORT.md)。本轮发现旧式公式排版、CID 标点、残留字符和特定 DSH 占位符失败，不能据先前合成件与主机接入验收宣称所有真实 PDF 均正常。上述是 1.3.0 开发阶段的历史记录，扩展验收未全部通过；不能替代当前版本的离线测试或真实质量验收。
