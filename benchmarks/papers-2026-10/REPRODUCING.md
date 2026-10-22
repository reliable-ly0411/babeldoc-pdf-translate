# 重放与检查

先读 [README](README.md) 的环境要求、许可及真实费用说明。使用同一 BabelDOC 0.6.4+pdftranslate.1 和可登录的 native 客户端。`cases/` 有 20 个完整参数例；`run_cases.py` 校验所有源 SHA256、改写为绝对本机路径、使用全新输出目录，并在失败后停止本批后续作业。默认仅规划，加 `--execute` 才运行模型。

```sh
python benchmarks/papers-2026-10/run_cases.py pilot-stein-codex \
  --destination /tmp/stein-plan --engine /path/to/babeldoc --codex-bin /path/to/codex
python benchmarks/papers-2026-10/run_cases.py full-r1-dsh \
  --destination /tmp/r1-live --engine /path/to/babeldoc \
  --dsh-package /path/to/deepseek-harness/apps/cli/package.json --node-bin /path/to/node --execute
```

首次复现不会拥有本次实验的私有译文缓存，耗时与 token 不应期待等于表中“重试成功”行。多个 case 在同一调用内串行执行并按后端/原文共享新缓存。需要手动续跑时保留旧缓存，复制本地 job、只改变 `output` 为新目录，不覆盖先前证据。内部 cache_dir 不是原生客户端的登录目录。

## 失败兼容性对照

`run_cases.py` 默认 dry-run 会在 destination 生成本机配置。先为该配置更换全新输出目录，再调用下列**显式实验**入口。它只增加指定的一个引擎 flag，仍执行引擎能力、目录和源检查；不是稳定作业模式中悄悄加入的新参数。

```sh
python benchmarks/papers-2026-10/run_probe.py /tmp/stein-plan/pilot-stein-codex.json \
  --engine /path/to/babeldoc --probe skip-formula-offset-calculation
# 确认本地输出/缓存设置后，加 --execute 运行。
# 第二对照：--probe disable-rich-text-translate，使用另一个全新输出目录。
```

实际尝试为 Stein skip-formula-offset-calculation、Stein disable-rich-text-translate、Dueling disable-rich-text-translate。DSH split-word 两次诊断复现没有改变模型/原文，目的仅是确认最终公开论文回答缺标记；不会把临时诊断的全文 native 消息保存为产品日志。纠正重试配置为 1 次，仍不合格则停止。

`fragment-en-fr-dsh-text` 与 `installed-zh-en-dsh-text` 是关闭表格翻译、min_text_length=1、sans-serif 的对照组合，目的是验证一个“纯文本优先配置”是否足以消除缺陷；不能据此单独归因三个参数中某一个。

## 回译与原创控制件

引擎会拒绝自身带 AI 翻译 Producer 标记的结果。本基准以 `prepare_roundtrip.py --help` 说明的显式方法创建独立副本，只改 Producer，逐页验证渲染一致；已固定的副本、变更前后哈希在 sources 与 roundtrip-preparation 报告中。不要直接覆盖初译输出，也不要在主适配器中自动取消该保护。

`make_fragments.py --destination /tmp/new-fragments` 用 ReportLab 创建原创英/中文控制件；`prompts/fragment-*.txt` 为可读源码。中文控制使用未嵌入的 STSong-Light CID 字体，专门保留已触发的视觉异常。扫描控制件为英文控制件以 PyMuPDF 2 倍矩阵渲染后，按原页尺寸插入空 PDF；只有一个图像，无文本层。其结果是明确的负例。重生成环境可能导致 PDF 元数据/对象字节不同，使用新文件应同步来源哈希，不能暗改固定输入。

## 验证

```sh
python -m unittest discover -s tests -v
python scripts/sync_plugin_skill.py --check
node --check scripts/dsh_chat.mjs
python benchmarks/papers-2026-10/audit_pdf.py \
  benchmarks/papers-2026-10/sources/stein2003.pdf \
  benchmarks/papers-2026-10/references/full-stein-codex/stein2003.no_watermark.zh-CN.mono.pdf \
  --report /tmp/stein-screening.json
cd benchmarks/papers-2026-10
sha256sum -c SHA256SUMS
```

`audit_pdf.py` 仅用于单语输出的资源、数字和尺寸筛查。必须另用 Poppler/PyMuPDF 渲染，至少检查各例 README 指明的风险页。全页缩略图只能发现大尺度问题，不证明小字号、数学式和术语全部正确。合成回归入口为 `tests/create_fixtures.py` 和 `tests/run_pdf_regression.py --help`；真实恢复实验入口为 `tests/run_native_recovery.py --help`，不应给合成回放附上真实模型质量结论。
