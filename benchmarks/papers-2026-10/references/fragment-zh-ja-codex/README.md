# fragment-zh-ja-codex

质量状态：**FAIL**；结构检查：**通过。

单页放大；未嵌入 CID 字体的部分中文句号视觉上变成 b，而 Unicode 提取为正确句号。

- 原文：[fragment-zh.pdf](../../sources/fragment-zh.pdf)；物理页：`all`。
- 方向：`zh-CN` → `ja`；后端：`codex`。
- 参考提示：[技术翻译指令](../../prompts/technical.txt)；[作业配置](../../cases/fragment-zh-ja-codex.json)。
- 耗时：79.197 秒；新译文请求 3 次，缓存命中 0 次。
- 原生 token（非字符估算）：`{"input_tokens": 32477, "cached_input_tokens": 16640, "cache_write_input_tokens": 0, "output_tokens": 327, "reasoning_output_tokens": 0}`。
- 完整执行指标：[JSON](../../reports/fragment-zh-ja-codex-run.json)；计量口径及限制见 [报告](../../REPORT.md)。

- [fragment-zh.no_watermark.ja.dual.pdf](fragment-zh.no_watermark.ja.dual.pdf)
- [fragment-zh.no_watermark.ja.mono.pdf](fragment-zh.no_watermark.ja.mono.pdf)

所有机器译文均为测试参考；FAIL 文件用于复现缺陷，LIMITED 仅表示有限抽查未见同类严重问题，不是人工校译通过。
