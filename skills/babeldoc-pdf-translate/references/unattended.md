# 本机聊天额度与无人值守翻译

`run --execute` 自动启动桥接、翻译并关闭本次创建的进程和端口，无需在聊天框中复制回复。开发和真实实验记录见 [Issue #8](https://github.com/reliable-ly0411/babeldoc-pdf-translate/issues/8)。原有兼容 API 的作业格式保持可用。

## 前置条件

- Python / BabelDOC 按 [部署说明](deployment.md) 安装并应用兼容补丁。
- Codex：CLI 须支持 `exec --ignore-user-config --ephemeral --output-schema`；`codex login status` 必须显示 `Logged in using ChatGPT`。桥接拒绝 API Key 登录。模型省略时使用 CLI 默认模型，也可指定账户可用的 `provider.model`。
- DSH：已安装含构建产物的 CLI、base、账户和 LLM 组件，并在 DSH 登录 **DeepSeek 模型账户**。Web 界面的本机登录不等于模型账户登录。默认使用 `deepseek-account`；只有用户明确选择复用现有 API 接口及余额时，才将 `route` 设为 `deepseek-official`。后一方式由 DSH 原生凭据服务解析 `DEEPSEEK_API_KEY`，不会要求在作业或聊天中提供密钥，也不在账户失败时自动回退。`dsh_package` 指向 CLI 的 `package.json`；源码构建为 `apps/cli/package.json`。`node_bin` 指向兼容该安装的 Node。
- 套餐必须允许相应模型调用；额度耗尽、退出登录或服务限流会失败，不绕过账户限制。

原生桥接的进程组清理在 Linux/POSIX 实验；其他系统需独立验收。DSH 使用已安装的组件接口，其升级可能导致接口变化，需重新探测和试译。已测版本与真实验收状态以 Issue #8 / VALIDATION.md 为准；模块导入成功不代表模型验收通过。

## 作业与运行

复制 `assets/job.codex.example.json` 或 `assets/job.dsh.example.json` 到工作目录，设置 PDF 与输出路径。相对路径基于作业文件目录；勿在只读插件缓存中保存作业输出。原生后端的 `workers`、`term_workers`、`qps` 固定为 1，填写其他值会拒绝。

```sh
python scripts/pdf_translate.py chat-doctor /path/to/job.json
python scripts/pdf_translate.py run /path/to/job.json --engine /path/to/babeldoc
python scripts/pdf_translate.py run /path/to/job.json --engine /path/to/babeldoc --execute
```

`chat-doctor` 只检查原生登录/组件，不翻译 PDF，也不证明远端推理成功。普通 `run` 是参数计划，不启动桥接。只有 `--execute` 调用已登录模型。已授权的多份文件可顺序运行独立作业；每份使用新输出目录，任一退出码非零时停止并检查清单。

| 原生 provider 字段 | 含义 |
|---|---|
| type | `codex` 或 `dsh` |
| model | Codex 可省略；DSH 默认 `deepseek-flash` |
| codex_bin | 仅 Codex；默认 `codex`，支持绝对路径 |
| route | 仅 DSH；默认 `deepseek-account`；明确选择 `deepseek-official` 会使用已配置官方 API 的余额 |
| dsh_package / node_bin | 仅 DSH；CLI 的 package.json 必填，Node 默认 `node` |
| timeout_seconds | 每次调用 5–1800 秒，默认 180 |
| retries | 可恢复传输错误或可纠正的格式/占位符错误重试 0–2 次，默认 1；鉴权、额度错误不重试 |
| cache_dir | 可选私有译文缓存；不填仅在本次进程中去重 |

原生 provider 不接受端点、密钥正文或密钥环境字段。DSH 当前仅适配官方端点与标准凭据引用，不自动读取其他 profile 的自定义网关。顶层 `timeout_seconds` 限制整个引擎执行（5–86400 秒，默认 7200），独立于每次模型调用。原生后端强制关闭 BabelDOC 翻译缓存，由桥接分别记录成功模型请求和缓存命中；普通 API 后端继续尊重 `ignore_cache`。

## 失败与恢复

账户未登录、超时、空答案、截断、无效 JSON、意外工具事件不能计为成功。只接受完整最终回答，不将中间思考当译文。桥接为批量输入提供逐段占位符数量清单，并拒绝遗漏、新增或改写的公式标记。临时传输错误，以及标记变更、批次不完整和 JSON 格式错误，最多在 `retries` 额度内重试；后几类重试会追加纠正要求，不盲目补回缺失公式。身份、额度错误不自动改路由。原生请求最终失败会终止引擎，避免 BabelDOC 回退原文后仍生成貌似成功的 PDF。退出码 1 为任务失败，2 为配置/启动错误，正常中断为 130。检查 `run-manifest.json` 的 `status`、`error`、`bridge.errors`、`live_requests`、`cache_hits`。

成功回复立即原子写入配置的缓存，文件权限 0600、目录 0700；仅保存请求哈希与回复，不保存请求原文。缓存键包含后端、模型、原生版本与完整翻译上下文，改变术语或提示会产生不同键。损坏或开放权限的缓存会拒绝。

BabelDOC 批量回复必须逐项返回完整、唯一的输入 ID；漏项或重复项直接失败。ASCII 赋值代码及被 `{vN}` 公式占位符拆开的标识符在请求前保护、回复后原样恢复，并校验占位符数量，防止 `sample_rate` 被误译。此规则覆盖受测代码形式，不是通用代码解析器；其他复杂语法仍需核验。

重试时保留 `cache_dir`，将 `output` 改为新目录再运行；已成功片段复用缓存，其余重新请求。缓存含译文，按用户保留要求管理，勿提交到 Git。旧输出不覆盖，中断清单和部分 PDF 保留诊断，不能当成成品。

## 耗时和 token 记录

执行清单的 `elapsed_seconds` 是整个作业的墙钟耗时，包含能力检查、PDF 处理、模型等待和输出检查。`bridge.request_metrics` 仅保存每次尝试的请求 SHA256、序号、耗时及原生 usage 字段，不保存提示正文或思考内容。失败重试的耗时包含退避等待。缓存命中不产生新的模型计量项。

`bridge.token_usage.native_counters` 分字段累加原生计数，不按字符估算。Codex 保留 `input_tokens`、`cached_input_tokens`、`output_tokens` 等原名；缓存、推理等细分项可能与总数重叠，不将这些字段全部相加。DSH 保留 `inputTokens`、`cacheReadTokens`、`cacheWriteTokens`、`outputTokens`、`totalTokens`：本次验证的 DSH 0.2.1-alpha.1 将 `inputTokens` 定义为未缓存输入，缓存读写另列，`totalTokens` 是含缓存的完整总量。不要用不同提供方的同名近似字段直接比较计费。模型未返回 usage、超时或被中断时记为 `unreported_calls`，表示未知，不能当作零消耗；`reported_calls` 统计实际收到计数的尝试（包括有计数的失败尝试）。这些数据不包含外围 agent 会话的消耗，也不是金额账单。

原生用量以桥接清单为准。兼容 HTTP 层没有将不同原生口径强行归一到 OpenAI usage；BabelDOC 自己的日志因而可能显示 token 为 0，这不能解释为原生账户没有消耗。

Ctrl-C / SIGTERM 关闭本次桥接和子进程；SIGKILL、断电、系统崩溃不能运行清理。此类异常后应先确认旧进程已结束，避免同一作业并行运行。

## 范围与数据

桥接只监听随机 `127.0.0.1` 端口，采用单任务随机令牌，通过临时私有文件交给 BabelDOC。Codex 使用独立空目录和只读沙箱，关闭 shell/apps/web/多代理/钩子/图像工具；DSH 只加载原生账户与 LLM 组件，没有 Agent、工具或会话持久化组件。不会从浏览器、日志或认证文件复制令牌，不导出个人提示词，不修改现有 Web 配置。原生客户端仍可进行正常认证状态维护；本包不保证客户端没有本机日志。

仅支持 BabelDOC 使用的非流式文本 Chat Completions 与文本/JSON 对象回复，不是通用 OpenAI API 替代品。解析排版本地执行，抽取文本仍发送给所选账户的云端模型。`needs-review` 表示调用及 PDF 结构检查通过，译文、数字和排版仍按 [quality.md](quality.md) 验收。不得把缓存回放或模拟客户端测试称为新的真实模型实测。

接口依据：[Codex 非交互调用](https://learn.chatgpt.com/docs/non-interactive-mode)、[Codex 登录](https://learn.chatgpt.com/docs/auth)、[DSH 账户模型组件](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek-account)、[DSH LLM](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm)。
