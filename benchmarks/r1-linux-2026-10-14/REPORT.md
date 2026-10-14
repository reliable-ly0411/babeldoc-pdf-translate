# Nature R1：Ubuntu 独立英中样稿与排版修复

2026-10-14，独立分支 `fix/linux-r1-layout-stability`。基线为远端 main
`2849110720e4c874b25cc1c69663b086c3051dee`，插件清单仍为 1.3.0；本分支未合并、
未发布 Release，也未把旧 Windows 候选版本当作已发布版本。Linux 目录独立，未修改
Windows 断点或虚拟机工作。

样稿采用 Nature 官方 **11 个物理页**，不是 arXiv 22/86 页版。输入 2,735,576 字节，
SHA256 `916fdaafc3b44143a9744481d079744f773d73d06372f82b1dba1076525927f2`。
完整来源、逐页 credit-line 核查、CC BY 4.0 和非官方改动说明见
[ATTRIBUTION.md](ATTRIBUTION.md)、[source.json](source.json)。

## 可交付文件

- [英中左右双语样稿](deepseek-r1.en-zh.sample.pdf)：11 页，左侧完整原文，右侧中文。
- [中文样稿](deepseek-r1.zh-CN.sample.pdf)：11 页，参考文献、作者/单位和许可按原文保留。
- [QA 报告 PDF](r1-linux-qa.pdf)、[逐页验收与哈希](qa-pages.json)。
- [每页渲染证据](pages/)、[图内文字目录](figure-text.json)、[坐标修订记录](region-edits.json)。

这是经过逐页检查并包含显式人工坐标修订的样稿。全文命令成功及 `needs-review`
不等于版式合格；脚本生成的原始 PDF 与最终样稿分开验收。

## 复现的问题及修复

1. **完整 JSON 仍可能缺译。** main 的 p3/9–11 真实试译在 12 个成功请求后失败；
   完整回复包含全部 6 个 ID，但标题续行被合并进前一行，该行 output 为空。
   首次普通槽列表方案又出现 2/3 槽变为 2/2，并把公式标记放进正文。
   两次实际失败已缩成公开离线回归夹具。改用原生 schema 的命名必填行/槽，
   ID、公式/样式/代码标记由程序恢复，空槽、漏项、重复项和新增标记拒绝，
   格式修正最多使用配置的有限重试次数。
2. **p3 数学破坏来自排版解析。** 使用真实引擎和原文逐字回传服务（35 请求，
   0 错误，无模型推理）仍能复现变量、根号和上标散落。六文件兼容补丁将
   检测表格内短数学 fallback 行连成二维公式对象，保留源字形、位置和曲线，
   防止普通斜体变量被当作可重排正文。四个几何回归测试核对字形/曲线归属、
   普通正文、无表格页和幂等性。跨公式的中文语序仍须核验：样稿显式重排了
   两处行内公式前后的中文，并按原比例复用了源公式对象。表 1 的解释注释合并了已生成的 Luna 文字，
   将原先 6/4.5 pt 两个碎片统一为 6.4 pt。
3. **p4 小数尾部误译。** 实际源输入把统计脚注的 `P < 0.01` 拆为
   `<style> P </style> {v5}.01).`，模型曾在 `.01` 前添“值为”。现在纯数值/标点
   尾部由程序逐字保留；只使受影响的 v3 检查点失效，其他成功检查点继续复用。
   真实源回传捕获与离线测试固定了这一输入。最终数字检查另核对表 2 的
   105 个数值单元格及统计阈值，不能仅凭正文中文覆盖通过判断。
4. **图内/图片文字不自动等于翻译完成。** p2/3 矢量图标签及 p9/10 图片图标签，
   使用 Luna 补译目录和已审阅坐标替换；曲线、刻度、模型 ID、变量和结果保持。
   p2/9 两个跨栏图题以完整图题再次由 Luna 翻译后按 a/b 分栏，避免“human participants”
   等源文本被跨栏拆开后产生中文悬空片段；p10 继续保留原排版中的行内数学对象。
   p11 原英文图片表格保留，下面增加完整中文转录；基数下标写成“63（13 进制）”，
   避免缺失字体字形，含义不变。此程序仅适用于该固定哈希论文，未宣称通用 OCR。
5. **中断产生的 PDF 不能当作成功。** 两次主机传输断开后适配器消失，孤立引擎
   曾留下部分英文回退输出和陈旧 running 清单；这些输出未交付。后续用独立
   观察进程运行并核对最终清单、中文覆盖和逐页视觉结果。最后一次未记录 usage
   的异常不能按零调用/零消费计。正常 SIGTERM 清理及检查点续跑另做了真实实验。
6. 固定 `bitstring==4.4.0`，避免 BabelDOC 0.6.4 的 `BitStream` 接口与 5.x 不兼容。

## 运行、回归与稳定性范围

环境：Ubuntu / Python 3.12.3、BabelDOC 0.6.4（CLI
`0.6.4+pdftranslate.linux-r1.1`）、PyMuPDF 1.28.2、bitstring 4.4.0、
Codex CLI 0.162.0-alpha.17.2。全部真实翻译使用已有 ChatGPT 登录，
`gpt-6-luna`、`reasoning_effort=low`；没有用高级模型替代翻译链路。
模型资产/字体身份及最终调用数见 [qa-pages.json](qa-pages.json)、
[run-summaries.json](run-summaries.json)。

- 六文件补丁完成 apply/check/rollback/reapply/check；77 项测试通过，Node 语法、
  27 项技能资源同步和 `git diff --check` 通过。
- 七组真实引擎合成回归全通过，22 份 PDF / 54 页；采用已审阅译文回放，
  **不计为新模型调用**。[synthetic-regression.json](synthetic-regression.json)。
- 修复后的第一轮完整数学版本：65 请求，50 缓存命中、15 次真实调用、0 失败。
  固定输入/配置/运行时的全篇缓存复跑：65 缓存命中、0 真实调用，两个版本的
  全部 11 页文字和 72 dpi 像素一致。文件字节因 PDF 内部元数据变化而不同。
  [repeat-comparison.json](repeat-comparison.json)。
- p7 的实际最小失败请求：空缓存一次通过，新桥接进程复跑命中缓存且回复哈希
  一致；另一个空缓存独立调用通过，措辞有差异，行/槽、标记及数值保持。
  不声称冷启动模型输出逐字确定，也没有声称全篇冷启动重复多轮稳定。
- 独立合成原生 SIGTERM 实验：2 次成功调用并保存检查点后中断，退出 130；
  续跑 2 个缓存命中 + 5 次真实调用，0 失败，原文不变。该实验在小数尾部修复前完成；
  数值修复不更改进程清理路径。
- 所有 11 页的双语英文半页与源稿 72 dpi 像素完全一致，
  [source-preservation.json](source-preservation.json)。

最终数值片段修复的全篇运行/缓存复跑结果与哈希以 `qa-pages.json` 中的
`final_run`、`final_repeat` 为准；之前的实测不混算成新的调用。

## 逐页验收

全部页用 Poppler 渲染并逐页查看；重点区域再放大。检查正文缺译、溢出重叠、
字号、视觉列顺序、根号/上标/变量、数值、图题引用、原英文和图内文字。

| 物理页 | 核验内容及结果 |
|---|---|
| 1 | 标题、摘要、双栏及 DOI 完整；无溢出。标题在“进行”中换行，保留为轻微排版差异。 |
| 2 | 两张训练曲线、轴标题/图例、图 1 图题及两栏正文完整；曲线/刻度未改。 |
| 3 | 表 1 各数学行与根号/上标检查；两处行内公式按源对象修正，碎片化注释字号统一；图 2 流程标签补译。 |
| 4 | 表 2 五个模型列顺序与 105 个数值单元格逐项核对；统计阈值 `P < 0.01` 保留。 |
| 5 | 正文、在线内容正常；参考文献及版权/许可/出版社说明按原文保留。 |
| 6 | 作者与单位按原文保留；只翻译页眉，未把英文作者页误报为中文缺失。 |
| 7 | GRPO 公式 (1)–(6)、分数/上下标/符号、两栏奖励设计与训练数据正常。 |
| 8 | 公式 (7)–(10)、跨页续文、数据/代码链接及补充信息正常；文献按原文保留。 |
| 9 | 两张频次曲线、坐标轴和图题补译；被统计的词 `Wait` 与例词仍作为原标识符。 |
| 10 | PPO/GRPO 节点及图例补译；箭头/边框/数学变量保留，无文字遮挡。 |
| 11 | 英文图片表格保留；完整中文提示词/评估转录无缺字，含 `\boxed{}`、根号及基数条件。 |

视觉阅读顺序按原文左页和译文右页、各页自上而下的双栏核对。输出未制作为带标签的
无障碍 PDF；覆盖/对象复用会使普通文本抽取含底层英文或重复内容，不能据此声称
屏幕阅读器的线性顺序已通过。图内文字的坐标修订、p11 转录及 p3 行内重排仍是
显式人工验收步骤。受测结论限于该输入、配置、字体/模型和 Linux 运行时；Windows
对照合并、其他 PDF、任意语言及全自动图片文字翻译需另验。

## 重现

先按项目部署说明建立独立 BabelDOC 0.6.4 环境，并使用本分支六文件补丁。
从旧五文件补丁升级时先用**旧包和旧清单**回滚，再应用新包；不要覆盖旧未提交工作。
该目录的 `job.codex.json`、提示词和术语表不含令牌或个人路径。

```sh
cd benchmarks/r1-linux-2026-10-14
mkdir -p work
curl --fail --location https://www.nature.com/articles/s41586-025-09422-z.pdf -o work/deepseekr1.pdf
sha256sum work/deepseekr1.pdf
# 确认上述固定哈希、11 页，再使用已授权的账户：
python ../../scripts/pdf_translate.py chat-doctor job.codex.json
python ../../scripts/pdf_translate.py run job.codex.json --engine /absolute/path/to/babeldoc --execute
python ../../scripts/repair_r1_regions.py work/deepseekr1.pdf work/full-01/deepseekr1.no_watermark.zh-CN.mono.pdf figure-text.json work/reviewed-01 --font-file /absolute/path/to/SourceHanSansCN-Regular.ttf
python ../../tests/check_r1_output.py work/deepseekr1.pdf work/reviewed-01/deepseek-r1.en-zh.reviewed-candidate.dual.pdf work/coverage.json
pdftoppm -png -r 100 work/reviewed-01/deepseek-r1.en-zh.reviewed-candidate.dual.pdf work/page
```

再以新 output 目录和相同 cache/config 重跑，比较逐页规范化文字和渲染像素，
并查看全部页面；不要仅比较文件是否存在。私有缓存、诊断、运行时、令牌和原生
事件日志不进入 Git。固定公开样稿是用户授权的 CC BY 例外，不放进技能安装载荷。
