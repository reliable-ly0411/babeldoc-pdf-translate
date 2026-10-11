# 未解决的 Stein 兼容性对照

这些是原文物理第 3、7 页的失败质量对照，并非合格译文。默认结果见 [pilot-stein-codex](../pilot-stein-codex/)。两次修改均未修复公式；关闭富文本时首字下沉更差。

- `pilot-stein-codex-offset.pdf`：增加 `--skip-formula-offset-calculation`，38.359 秒，10 次缓存命中，无新模型调用。
- `pilot-stein-codex-plain.pdf`：增加 `--disable-rich-text-translate`，221.440 秒，7 次新调用、3 次缓存命中。

对应指标在 `../../reports/pilot-stein-codex-{offset,plain}-run.json`；操作方法见 [兼容性实验](../../REPRODUCING.md)。
