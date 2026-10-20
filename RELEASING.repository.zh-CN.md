# babeldoc-pdf-translate 仓库补充

本文件仅定义本仓库的分支、版本映射与上游例外；与通用规范一并读取。具体任务、检查结果和整改进度不写在本文件。

## 分支映射
- 维护/集成入口为 `main`；`dev/paper-benchmark-20261011` 与 `fix/linux-r1-layout-stability` 是专项分支，不自动等同于永久通用开发线。
- 新的长期开发线名称未约定；专项继续使用不与现有 ref 冲突的 `dev/`、`fix/`、`docs/`。

## 版本与产物映射
- 插件版本在 `plugin.json` 和 `.codex-plugin/plugin.json` 中保持一致，标签为 `v` 加插件版本，先行版本使用 `-rc.N`。
- 插件版本、BabelDOC 引擎上游版本、引擎补丁身份分别记录；版本关系见 `references/versioning.md`。
- 插件源码安装包为 `babeldoc-pdf-translate-v<版本>.zip`，DSH 独立技能包若发布则保留其目标身份；不将源码 ZIP 冒称自带 Python/模型的安装器。
- 项目不是单纯汉化发行，不强加 `-zh-CN`。

## 上游与适用例外
- 这是独立插件/技能与 BabelDOC 适配项目，不是直接把 BabelDOC 的版本号变为本仓插件版本。
- 上游衍生补丁遵守 AGPL-3.0；原创适配代码按其 MIT 许可，依赖与素材各自许可不互相覆盖。
- 上游说明按实际对应引擎基线引用，不把所有依赖历史日志混成插件发行说明。
