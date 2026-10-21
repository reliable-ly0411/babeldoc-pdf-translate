# Fixture provenance

`r1-batch-failure.json`, `r1-slot-failure.json`, and
`r1-math-geometry.json` derive from Guo et al., *DeepSeek-R1 incentivizes
reasoning in LLMs through reinforcement learning*, Nature 645, 633–638 (2025),
DOI [10.1038/s41586-025-09422-z](https://doi.org/10.1038/s41586-025-09422-z).
© The Author(s) 2025, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The fixed official 11-page PDF SHA256 is
`916fdaafc3b44143a9744481d079744f773d73d06372f82b1dba1076525927f2`.

The first two fixtures contain public source excerpts and the actual rejected
Luna reply shape/content. They reproduce row/slot merging without an account.
The geometry fixture is a reduced source intermediate representation of the
page 3 table, stripped of unrelated metadata and long drawing instructions.
These are test adaptations, not official translations or author endorsements.
Test code follows the repository license; the source-paper material retains
its CC BY license. No native account events, private prompts, or credentials
are included.

`l1quad-prose-semantics.json` contains three actual source/response row pairs
from the independent rc.4 p5 cold run, reproduced with eight real cache hits
and zero native inference. They derive from Wu et al., L1Quad v2,
https://arxiv.org/abs/2302.07208v2, CC BY4.0. The source PDF SHA256 is
94dd7e348e662de63ef01c4cd6c6529b37c464464df989ef3ced35e0f44cb7f3.
The rows show why exact marker/numeric/name fidelity does not establish prose
translation accuracy. Counterexamples are engineering reference wording,
not independently accepted model outputs or an official paper translation.

`l1quad-reference-connector.json` retains the actual D04 row and its final
complete-pair semantic finding from the six-call rc.5 round. All original
markers are present, yet the explicit relation to equation(13) is omitted.
The fixture verifies that a validated discrepant/uncertain semantic screen
keeps acceptance blocked even when literal/marker checks pass. It is evidence,
not a paper-specific detection or translation rule. Source attribution and
license are embedded in the fixture.


This experimental branch retains the historical `r1-math-geometry.json` fixture.
The large `l1quad-inline-math.json` source-geometry extract is not bundled. They remain optional external
validation data under `BABELDOC_EXTRA_TEST_DATA`; their test outcomes are reported
separately. Other `l1quad-*` and semantic regression excerpts retain the same
L1Quad v2 source attribution above. No complete source paper or native-event
archive is included in this fixture directory.
