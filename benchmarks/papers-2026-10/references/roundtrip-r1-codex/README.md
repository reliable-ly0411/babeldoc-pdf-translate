# roundtrip-r1-codex

质量状态：**FAIL**；结构检查：**通过。

只选固定中文输入第 2 页（原论文第 7 页）；方法标题未译、英文单词断裂，式 (5) 下标串移到末尾。

- 原文：[roundtrip-r1-zh.pdf](../../sources/roundtrip-r1-zh.pdf)；物理页：`2`。
- 方向：`zh-CN` → `en`；后端：`codex`。
- 参考提示：[技术翻译指令](../../prompts/technical.txt)；[作业配置](../../cases/roundtrip-r1-codex.json)。
- 耗时：218.271 秒；新译文请求 8 次，缓存命中 0 次。
- 原生 token（非字符估算）：`{"input_tokens": 88671, "cached_input_tokens": 66560, "cache_write_input_tokens": 0, "output_tokens": 1852, "reasoning_output_tokens": 0}`。
- 完整执行指标：[JSON](../../reports/roundtrip-r1-codex-prepared-run.json)；计量口径及限制见 [报告](../../REPORT.md)。

- [roundtrip-r1-zh.no_watermark.en.dual.pdf](roundtrip-r1-zh.no_watermark.en.dual.pdf)
- [roundtrip-r1-zh.no_watermark.en.mono.pdf](roundtrip-r1-zh.no_watermark.en.mono.pdf)

所有机器译文均为测试参考；FAIL 文件用于复现缺陷，LIMITED 仅表示有限抽查未见同类严重问题，不是人工校译通过。
