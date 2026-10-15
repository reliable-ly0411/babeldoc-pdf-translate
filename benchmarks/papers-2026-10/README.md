# 复杂论文 PDF 翻译回归（2026-10）

插件版本保持 **1.3.0**。本目录用于复现实验、比较结果和定位缺陷，不是人工校译论文集。原文、使用的参考提示词、逐项作业及机器生成参考输出一起保留；原文许可见 [ATTRIBUTION.md](ATTRIBUTION.md)，下载地址和哈希见 [sources.json](sources.json)。

## 语料选择

| 论文 | 页数 | 选择理由与版式风险 |
|---|---:|---|
| Stein, Respect the Unstable (2003) | 14 | 控制理论基本限制、航空器不稳定性；老式 Type 1 字体、首字下沉、侧栏、积分、行内根号、多栏、历史照片和曲线。用户指定并确认再分发和整篇翻译授权。 |
| Champion-level drone racing using deep reinforcement learning (2023) | 14 | 航空与 AI 交叉；无人机照片、赛道、坐标图、四旋翼动力学、矩阵、多列表格及扩展数据。 |
| Dueling Network Architectures for Deep Reinforcement Learning (2016) | 9 | 深度强化学习的重要网络结构；双栏、价值/优势函数、Atari 图片、密集曲线和比较表格。 |
| Nature DeepSeek-R1 article (2025) | 11 | 大模型强化学习推理；多面板评测图、GRPO 数学式、参考文献、作者信息、扩展数据。 |

全文测试以英语到中文为主。中文到英文使用上述机器译文进行回译，明确标为 round-trip：它能检验中文输入与英文排版，但不是独立中文论文，也不能用相似度证明最初翻译无误。法语和日语仅使用项目自行编写的单页短片段，不扩展到整篇其他语言翻译。

完整结果见 [实验报告](REPORT.md)，逐个操作见 [复现说明](REPRODUCING.md)。

## 文件

- `sources/`：下载时的原始 PDF，以及有源码的简短合成控制件。
- `prompts/technical.txt`：实际使用的通用技术翻译提示；`en-zh-glossary.csv`：控制与 AI 术语表；`fragment-*.txt`：短片段可读原文。
- `cases/`：相对路径作业，DSH 路径需替换为本机安装；不含凭据。
- `references/`：参考译文、双语输出和必要的失败/缺陷证据；逐个结果以实验报告的状态为准。
- `reports/`：环境、真实耗时和原生 token 字段、功能覆盖与版式审阅。

## 复现

安装仓库规定的运行时并通过 `repair_runtime.py --check`，然后使用运行时自己的 Python。先做代表页，随后做全文；每次使用全新目标目录。默认仅 dry-run，真正调用模型必须加 `--execute`。DSH 作业中的 `deepseek-official` 会使用当前配置的官方 API 余额，需由运行者明确授权；Codex 使用本机 ChatGPT 登录。

```sh
python benchmarks/papers-2026-10/run_cases.py pilot-stein-codex \
  --destination /tmp/papers-codex-plan --engine /path/to/babeldoc \
  --codex-bin /path/to/codex
python benchmarks/papers-2026-10/run_cases.py pilot-swift-dsh \
  --destination /tmp/papers-dsh-live --engine /path/to/babeldoc \
  --dsh-package /path/to/deepseek-harness/apps/cli/package.json \
  --node-bin /path/to/node --execute
```

运行器串行执行所选作业，校验原文 SHA256，任何失败后停止本批后续作业。所有私有缓存、完整执行日志和本机路径配置留在新目标目录。中文回译和法语/日语回译使用 `sources/roundtrip-*.pdf` 固定输入。引擎原本禁止二次翻译自己的输出；本实验明确调用 `prepare_roundtrip.py` 创建独立副本，仅调整 Producer 元数据，不改变页面，并逐页验证渲染一致。原始参考译文保留，前后哈希和变更在 `reports/roundtrip-preparation.json`；正常适配器不会隐式移除该保护。重新生成参考译文后可显式重做这一步。

## 计量与验收

耗时为单项作业墙钟时间，包含原生客户端启动、PDF 分析、模型调用和排版。并发执行的不同作业不能简单相加当作整场实验历时。失败试验和修复耗时也保存。`live_requests` 是成功的新译文请求；实际尝试次数由 `attempts` 给出。成功缓存命中不重复计入模型 token。

Codex 和 DSH 的原生 usage 字段分开保存。DSH 本次版本的 `inputTokens` 为未缓存输入，`totalTokens` 包含缓存输入与输出；Codex 的输入、缓存输入、输出字段分别列出，不将可能重叠的细分字段相加。缺失的 usage 是未知消耗，不能当零。数据不包含外层编排 agent 的会话消耗，也不等于金额账单。Codex CLI 默认模型未固定到不可变版本、DSH 使用 `deepseek-flash` 别名，因此复现不保证逐字或逐 token 一致。

结构通过要求源哈希不变、请求变体齐全、PDF 可解析、页数和尺寸符合选页及双语布局。质量审阅另外检查图形、公式、负号、单位、覆盖和术语；两类结论分别记录。图片内部的英文不属于可提取文字翻译，不能因设置 `translate_tables` 就宣称像素表格已译。回放合成件验证管线，不算真实模型质量证据。
