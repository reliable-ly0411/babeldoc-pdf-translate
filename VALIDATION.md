# Validation status

Current development candidate: **1.5.0-rc.25**. Source publication is separate
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


Current rc.25 public profile: **614 tests, 584 passed, 30 explicitly reported
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

An independent all-page review found one remaining PDF release blocker on page 3:
translated prose overlaps the end of an inline formula. Code publication remains
a draft while the generic layout fix and candidate recheck are pending.
