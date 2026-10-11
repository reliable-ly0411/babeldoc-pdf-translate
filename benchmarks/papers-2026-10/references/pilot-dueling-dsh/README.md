# pilot-dueling-dsh

质量状态：**FAIL**；结构检查：**失败。

原文 4、8 页；DSH 丢失 split-word 内的 {v1}。保护校验终止，未生成可验收 PDF。

- 原文：[dueling2016.pdf](../../sources/dueling2016.pdf)；物理页：`4,8`。
- 方向：`en` → `zh-CN`；后端：`dsh`。
- 参考提示：[技术翻译指令](../../prompts/technical.txt)；[作业配置](../../cases/pilot-dueling-dsh.json)。
- 耗时：33.428 秒；新译文请求 8 次，缓存命中 0 次。
- 原生 token（非字符估算）：`{"inputTokens": 5270, "outputTokens": 2680, "cacheReadTokens": 3712, "cacheWriteTokens": 0, "totalTokens": 11662}`。
- 完整执行指标：[JSON](../../reports/pilot-dueling-dsh-run.json)；计量口径及限制见 [报告](../../REPORT.md)。

没有合格输出 PDF；这里保留失败预期与执行记录。

所有机器译文均为测试参考；FAIL 文件用于复现缺陷，LIMITED 仅表示有限抽查未见同类严重问题，不是人工校译通过。
