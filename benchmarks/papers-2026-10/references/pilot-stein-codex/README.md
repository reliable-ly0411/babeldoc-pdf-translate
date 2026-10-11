# pilot-stein-codex

质量状态：**FAIL**；结构检查：**通过。

原文 3、7 页均放大检查；积分/根号错位。两次兼容性修复未改善。

- 原文：[stein2003.pdf](../../sources/stein2003.pdf)；物理页：`3,7`。
- 方向：`en` → `zh-CN`；后端：`codex`。
- 参考提示：[技术翻译指令](../../prompts/technical.txt)；[作业配置](../../cases/pilot-stein-codex.json)。
- 耗时：253.733 秒；新译文请求 10 次，缓存命中 0 次。
- 原生 token（非字符估算）：`{"input_tokens": 111423, "cached_input_tokens": 49920, "cache_write_input_tokens": 0, "output_tokens": 2788, "reasoning_output_tokens": 17}`。
- 完整执行指标：[JSON](../../reports/pilot-stein-codex-run.json)；计量口径及限制见 [报告](../../REPORT.md)。

- [stein2003.no_watermark.zh-CN.dual.pdf](stein2003.no_watermark.zh-CN.dual.pdf)
- [stein2003.no_watermark.zh-CN.mono.pdf](stein2003.no_watermark.zh-CN.mono.pdf)
- [stein2003.zh-CN.dual.pdf](stein2003.zh-CN.dual.pdf)
- [stein2003.zh-CN.mono.pdf](stein2003.zh-CN.mono.pdf)

所有机器译文均为测试参考；FAIL 文件用于复现缺陷，LIMITED 仅表示有限抽查未见同类严重问题，不是人工校译通过。
