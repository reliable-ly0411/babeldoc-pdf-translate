# 航空航天与人工智能 PDF 翻译实验报告

2026-10-11；插件 **1.3.0**；开发分支 `dev/paper-benchmark-20261011`；跟踪 [Issue #10](https://github.com/reliable-ly0411/babeldoc-pdf-translate/issues/10)。

**结论：两端原生桥接及中断续跑可用，复杂论文质量未全部通过，暂不合并主线。** 已保存 4 篇原论文共 48 页、20 个可重放测试例、全文/代表页/回译/短片段输出，以及失败记录。`FAIL` 参考文件用于复现缺陷；`LIMITED` 仅表示有限抽查未发现同类严重问题，均不是人工校译的成品。

## 环境与来源

Linux 7.0.0-34-generic，AMD Ryzen 7 6800H，约 14.81 GiB 可见内存；Python 3.12.3、BabelDOC 0.6.4+pdftranslate.1、PyMuPDF 1.28.2、Poppler 26.05.0、Node 24.20.0。CPU 版式推理；模型/字体缓存已预热；每个翻译作业单 worker，部分独立作业重叠运行。逐项环境在 [environment.json](reports/environment.json)。耗时不能作为不同模型的公平速度排名。

- Codex CLI 0.162.0-alpha.17.2，使用本机 ChatGPT 登录额度；CLI 默认模型没有固定到不可变版本。
- DSH 0.2.1-alpha.1，模型别名 `deepseek-flash`；按用户明确选择复用当前 `deepseek-official` 接口及余额。这不是 DeepSeek 订阅账户额度。
- 两端安装目录已部署同版本开发代码并核对哈希，保留本机旧文件备份。此轮安装态证据为真实 native 客户端和已安装脚本调用，不等于重新完成桌面 GUI 全流程验收。市场索引仍引用原有主线版本，未发布新版本。

通过公开出版页面和作者站点选择 4 篇具有代表性的论文：Stein《Respect the Unstable》、无人机竞速 Swift、Dueling Network、Nature 版 DeepSeek-R1。来源、原始 SHA256、页数、下载日期在 [sources.json](sources.json)，具体署名与许可在 [ATTRIBUTION.md](ATTRIBUTION.md)。Stein 依据维护者明确确认的原文再分发及全文翻译授权收录，未标为 CC 许可；其余三篇按各自 CC BY 4.0 信息署名。全部原文保持下载时字节不变。

中文到英文包含 Swift 全文回译、R1 公式代表页回译和项目原创中文控制件。法语、日语只用项目原创单页短片段及回译，不把模型译文称为独立中文论文或人工标准答案。

## 测试例与实测结果

每项链接中均有原文、有效作业设置、提示词、参考 PDF、耗时及原生 token。`I/C/O` 为 Codex 原名 input/cached_input/output；`T` 为 DSH totalTokens。缓存输入等细项不重复加入总数。`新调用` 指成功产生新译文的请求；有计数的失败尝试也纳入 token，详见逐次 run JSON。

| 测试例 | 方向/物理页 | 秒 | 新调用/缓存 | 原生 token | 结构 / 质量 |
|---|---|---:|---:|---|---|
| [full-stein-codex](references/full-stein-codex/) | en→zh-CN / all | 2061.439 | 78/0 | I=866,369; C=499,200; O=19,276 | 通过 / FAIL |
| [full-dueling-codex](references/full-dueling-codex/) | en→zh-CN / all | 2325.126 | 105/2 | I=1,156,649; C=690,560; O=19,148 | 通过 / FAIL |
| [full-swift-dsh](references/full-swift-dsh/) | en→zh-CN / all | 278.493 | 51/97 | T=80,849 | 通过 / LIMITED |
| [full-r1-dsh](references/full-r1-dsh/) | en→zh-CN / all | 165.373 | 68/0 | T=87,476 | 通过 / LIMITED |
| [pilot-stein-codex](references/pilot-stein-codex/) | en→zh-CN / 3,7 | 253.733 | 10/0 | I=111,423; C=49,920; O=2,788 | 通过 / FAIL |
| [pilot-dueling-dsh](references/pilot-dueling-dsh/) | en→zh-CN / 4,8 | 33.428 | 8/0 | T=11,662 | 失败 / FAIL |
| [pilot-swift-dsh](references/pilot-swift-dsh/) | en→zh-CN / 2,7,14 | 56.393 | 17/0 | T=23,583 | 通过 / LIMITED |
| [pilot-r1-codex](references/pilot-r1-codex/) | en→zh-CN / 2,7 | 288.970 | 11/0 | I=123,147; C=33,280; O=3,717 | 通过 / LIMITED |
| [roundtrip-swift-dsh](references/roundtrip-swift-dsh/) | zh-CN→en / all | 484.986 | 94/7 | T=98,884 | 通过 / FAIL |
| [roundtrip-r1-codex](references/roundtrip-r1-codex/) | zh-CN→en / 2 | 218.271 | 8/0 | I=88,671; C=66,560; O=1,852 | 通过 / FAIL |
| [fragment-en-fr-dsh](references/fragment-en-fr-dsh/) | en→fr / all | 23.129 | 3/0 | T=2,192 | 通过 / FAIL |
| [fragment-fr-en-dsh](references/fragment-fr-en-dsh/) | fr→en / all | 23.307 | 3/0 | T=2,324 | 通过 / FAIL |
| [fragment-zh-ja-codex](references/fragment-zh-ja-codex/) | zh-CN→ja / all | 79.197 | 3/0 | I=32,477; C=16,640; O=327 | 通过 / FAIL |
| [fragment-ja-zh-codex](references/fragment-ja-zh-codex/) | ja→zh-CN / all | 87.775 | 3/0 | I=32,607; C=24,960; O=350 | 通过 / FAIL |
| [installed-zh-en-dsh](references/installed-zh-en-dsh/) | zh-CN→en / all | 23.920 | 4/0 | T=2,513 | 通过 / FAIL |
| [fragment-en-fr-dsh-text](references/fragment-en-fr-dsh-text/) | en→fr / all | 20.967 | 2/1 | T=1,883 | 通过 / FAIL |
| [installed-zh-en-dsh-text](references/installed-zh-en-dsh-text/) | zh-CN→en / all | 20.057 | 2/2 | T=1,832 | 通过 / FAIL |
| [scan-off-dsh](references/scan-off-dsh/) | en→zh-CN / all | 10.754 | 0/0 | 无模型调用 | 失败 / FAIL |
| [scan-auto-dsh](references/scan-auto-dsh/) | en→zh-CN / all | 10.653 | 0/0 | 无模型调用 | 失败 / FAIL |
| [scan-force-dsh](references/scan-force-dsh/) | en→zh-CN / all | 9.695 | 0/0 | 无模型调用 | 失败 / FAIL |

Swift 全文成功行是修复后执行：此前完整作业已花费 **397.654 秒、83,314 个已报告 DSH token**，因批次不完整失败；之后复用 97 次缓存，花费 **278.493 秒、80,849 个 token** 完成。不能把后者当作从零翻译耗时。代表页 pilot 的成本另列。R1 回译固定输入有 2 页，本次只选择输入第 2 页，即原论文物理第 7 页。

## 功能覆盖

| 功能 | 证据 | 结论 |
|---|---|---|
| Codex / DSH 无人值守 native 调用 | 两端真实论文、短片段，安装态调用 | 集成通过；DSH Dueling 内容保护失败单列 |
| 全文 / 非连续选页 / 晚页 / 分块 | 48 页主语料；3,7 / 2,7 / 4,8 / 2,7,14；max_pages_per_part=5；合成回归 | 输出结构检查通过的案例均保留记录 |
| mono / 双语左右 / 双语交替 / 译文在前 | 主语料与 Swift 28 页交替回译、合成件 | 结构通过；版式质量另判 |
| 无水印 / 水印 / 同时两种 | Stein pilot 四个变体；合成件 | 变体、页数和尺寸验证通过 |
| 术语提示 / 自定义 CSV / 自动术语保存再校验 | 实际 technical.txt、领域 CSV；Swift 146/706 行候选表 | 功能通过；候选术语不等于专业审定 |
| serif / sans-serif / 默认字体 | 代表页、文字配置对照 | 参数执行；CID 标点和混排仍有缺陷 |
| 可提取表格 / 图片 / 公式 | 数字资源筛查、全页缩略图、重点放大 | 资源保留；不能据此判定公式、像素表格已正确翻译 |
| 扫描 off / auto / force | 原创文字栅格化单页，3 种模式 | 此环境均无段落、无输出；未实现通用整页 OCR |
| 源文件不覆盖 / 输出目录保护 / 参数及凭据校验 | 源 SHA、适配器测试 | 通过 |
| 缓存 / 失败保护 / 有界重试 | 真实失败与恢复、保护标记测试 | 格式或占位符错误可纠正重试；持续错误仍拒绝 |
| 取消与恢复 | Codex、DSH 各真实 SIGTERM 一次 | 中断退出 130，均复用 2 条 checkpoint 后续跑成功 |
| 程序回归 | 64 项单元测试，7 项真实引擎合成回放 | 64/64、7/7 通过；合成回放没有模型推理 |

自动计数和结构检查不能替代译文审阅。四份全文 mono 的解码栅格图片匹配均未发现源图片实例缺失；这不覆盖矢量路径、坐标、层叠或图片内文字准确性。双语归档文件仅进行了无损对象去重压缩，逐页 72 dpi 渲染和提取文本与压缩前一致，详情见 [packaging.json](reports/packaging.json)。归档后文件哈希以 [artifacts.json](reports/artifacts.json) 和 `SHA256SUMS` 为准。

## 未通过项目与修复边界

1. **Stein 数学排版**：原文物理第 3 页 Bode 积分/根号重叠或错位，第 7 页行内倒立摆公式破损。分别尝试跳过公式偏移计算和关闭富文本；两次均未解决，后者首字下沉更差。保留默认输出与两次对照，不作为数学保真验收通过。
2. **DSH Dueling 占位符**：模型丢掉 `advan- {v1}tage` 中的 `{v1}`。增加逐行 token 数量契约、一次纠正重试，以及关闭富文本的对照后仍失败。桥接正确拒绝 `PROTECTED_TEXT_CHANGED`，不伪造补回公式。Codex 全文虽然完成，首标题和部分行内碎片仍有混排。
3. **中文、日文 CID 标点与短片段残留**：原创 PDF 的句号在提取文本中正确，译文渲染却显示成 b/C；法国文片段出现 KConservez…d。文本配置对照未达到可交付质量。原始控制件的行框位于页面内，不能把这类问题简单归咎为输入裁切。
4. **回译覆盖与公式退化**：Swift 回译多页仍有中文段落、图注和短标题；R1 的“方法”未译，式 (5) 下标移到末尾，英文出现断词。短文本阈值可能影响部分标题，但尚未证明全部残留段落的根因。回译不是初译正确性的证明。
5. **扫描和像素文字**：Swift 第 14 页表格、R1 第 10–11 页图像内英文保留；整页扫描控制件 3 种模式均失败。引擎可能返回 0，但适配器因缺少所需 PDF 标记失败并向调用者返回非零。

Swift 批次不完整已通过保留检查点后重试恢复；原始失败消耗仍保留。详细缺陷与对照见 [known-failures.json](reports/known-failures.json) 和 [quality-review.json](reports/quality-review.json)。

可视证据：[Stein 原始积分](reports/images/stein-p3-source-integrals.png) / [译后积分](reports/images/stein-p3-translated-integrals.png)；[CID 原始控制件](reports/images/cid-source.png) / [译后标点](reports/images/cid-translated.png)；[法语残留](reports/images/fragment-fr-residue.png)；[Dueling 标题](reports/images/dueling-title.png)。

复查遵循仓库 [SKILL.md](../../SKILL.md) 第 5 步："after two unsuccessful targeted repairs, retain the best result and describe affected pages and options." 因此保留失败页及对照，不继续无界整篇重译。后续应针对公式识别/字形恢复、混合字体分段和中文回译覆盖建立最小回归后再修引擎；这些问题未解决前，用户要求的“两端测试通过再合并”条件未满足。

## 耗时、token 与代码变更

共归档 **29 个执行清单**，另有两端中断/续跑两阶段记录。合计为下列原生计数，已包括失败、诊断、兼容性试验和恢复；不包括外围编排对话。至少 3 次尝试没有 usage，不能按零消耗计算，也不能从这些字段推导金额账单。

| 后端 | 已报告 / 未报告尝试 | 原生字段累计 |
|---|---:|---|
| Codex | 228 / 1 | input_tokens 2,522,285；cached_input_tokens 1,431,040；output_tokens 49,868；reasoning_output_tokens 1,357；cache_write_input_tokens 0 |
| DSH | 359 / 2 | inputTokens 239,474；cacheReadTokens 97,920；outputTokens 96,460；totalTokens **433,854**；cacheWriteTokens 0 |

Codex 各细分项可能与总项重叠，不求和制造“总消耗”；DSH 本版本的 inputTokens 是未缓存输入，totalTokens 包含缓存与输出。各作业墙钟耗时包含启动、解析、模型与排版，可能互相重叠。桥接 HTTP 兼容层没有强行归一不同原生计量；BabelDOC 日志显示的 0 token 不能当成账户无消耗。完整累积方式在 [usage-summary.json](reports/usage-summary.json)。

本分支在 1.3.0 内补充原生 usage、每次尝试耗时/请求哈希、总作业耗时、逐段占位符数量约束及有界纠正重试；不记录 native 私有提示、推理或凭据。原始模型缓存、配置及完整运行日志留在本机，不纳入仓库。64 项测试覆盖重复缓存不重复计数、未知 usage、格式修复上限、禁止新增/丢失公式标记等关键行为；本次没有发布新 tag 或膨胀版本号。

复现操作与失败对照见 [REPRODUCING.md](REPRODUCING.md)，参考请求见 [prompts/user-requests.zh.md](prompts/user-requests.zh.md)。
