# BabelDOC PDF Translate — 通用 Agent 技能

入口：[SKILL.md](SKILL.md)。这是可分发的技能与脚本包，不是包含所有模型和依赖的独立翻译软件。

适用于支持文件访问和命令执行的 agent 平台；核心不依赖 Codex 工具。`agents/openai.yaml` 是可选界面元数据，其他平台可忽略。

## 快速使用

1. 将整个 `babeldoc-pdf-translate` 目录复制到目标平台支持的技能目录；若没有技能机制，让 agent 读取 SKILL.md。
2. 按 [部署说明](references/deployment.md) 配置 BabelDOC 运行时。
3. 告诉 agent PDF 路径、目标语言和偏好；服务未配置时也可先准备术语和作业草案。

示例请求：

> 使用这个技能把论文第 2–4 个物理页翻译为中文，输出交替页中英对照，只保留选中页。phase margin 固定翻译为相位裕度，其余术语结合控制领域上下文自动匹配。保留公式、图片和单位。云端接口稍后配置，先准备作业和术语表。

> 翻译整份 PDF，输出中文单语及左右对照两个版本。航空专有名词采用英文（中文），使用我提供的 CSV；先试译有公式和表格的两页。

## 包结构

```text
SKILL.md              agent 入口与工作流程
scripts/              参数校验、引擎探测、PDF 检查与执行
references/           参数、术语、质量、部署和来源
assets/               作业、术语表、提示词模板
agents/               可选的平台界面元数据
requirements.txt      已测运行时版本基线
```

支持单双语、双语页顺序、页码、术语表、自动术语提取、风格提示、字体、扫描处理、并发和云端兼容接口。专业领域判断由 agent 结合上下文完成；本包不自带各行业权威词库，不保证复杂 PDF 完全免返工。

运行与测试边界见 [VALIDATION.md](VALIDATION.md)。不要在分发包中加入个人密钥、PDF、缓存或虚拟环境。
