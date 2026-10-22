# fragment-ja-zh-codex

质量状态：**FAIL**；结构检查：**通过。

单页放大；b/C 残留、鬼影和标识符连字符变化，不能仅凭文本抽取判定保真。

- 原文：[roundtrip-ja.pdf](../../sources/roundtrip-ja.pdf)；物理页：`all`。
- 方向：`ja` → `zh-CN`；后端：`codex`。
- 参考提示：[技术翻译指令](../../prompts/technical.txt)；[作业配置](../../cases/fragment-ja-zh-codex.json)。
- 耗时：87.775 秒；新译文请求 3 次，缓存命中 0 次。
- 原生 token（非字符估算）：`{"input_tokens": 32607, "cached_input_tokens": 24960, "cache_write_input_tokens": 0, "output_tokens": 350, "reasoning_output_tokens": 33}`。
- 完整执行指标：[JSON](../../reports/fragment-ja-zh-codex-prepared-run.json)；计量口径及限制见 [报告](../../REPORT.md)。

- [roundtrip-ja.no_watermark.zh-CN.dual.pdf](roundtrip-ja.no_watermark.zh-CN.dual.pdf)
- [roundtrip-ja.no_watermark.zh-CN.mono.pdf](roundtrip-ja.no_watermark.zh-CN.mono.pdf)

所有机器译文均为测试参考；FAIL 文件用于复现缺陷，LIMITED 仅表示有限抽查未见同类严重问题，不是人工校译通过。
