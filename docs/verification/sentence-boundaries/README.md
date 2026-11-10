# 换行与断句专项验收

Issue [#90](https://github.com/wax0629/WaxTranslate/issues/90)。基线 main `a79d70a`。Mac `2493b3b` 当前提交验收通过后才开始 Windows `c298418`；两端独立门禁均成功。完整提交、CI、包和测试计数见[机器可读证据](evidence.json)。

## 契约与样例

[共享 JSON](../../../Tests/Fixtures/sentence-boundaries.json) 有 **91 个基础场景、13 类**：续行、误拼、列表、注释、代码、标题、语言断句、成对标点、多语、精确偏移、跨行词、完整性、独立词条。场景标记具体命中位置和预期范围，不在生产代码中按样例词特判。另有重新折行、1×/1.5×/2×、负坐标和平移、识别块乱序变换，共 **160 项**范围/策略检查。

验收包含同一行被 OCR 拆成多块、重叠块重复词、列表续行、缩进新段、注释与代码隔离、缩写与小数/版本/URL、引号内问句及归属语、中日韩法续行、重复词/emoji/组合重音、软/硬连字符、无省略号裁切和未知边界。完整性不依赖词典或术语是否命中。

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 同语料旧基线 | 复现误拼、截断与半句 | a79d70a 对 91 个基础范围/策略检查仅 51 通过、40 失败；旧版无完整性字段，未将该字段计入比较 | [基线报告](baseline-report.json)，失败已复现 |
| Mac 新管线 | 来源范围、结构、偏移和触发符合契约 | 91 个基础项与 69 个变体共160/160通过，涵盖上述13类 | [当前报告](mac-report.json)，通过 |
| 真实 Vision | 实际图像经过识字后归并、断句和判断片段 | 22项明暗/系统及等宽字体检查通过；15项完整、6项明确裁切、1项OCR遗漏句号而安全保持未确认，不补造标点 | [原始输出](vision/observations.json)，分别记录 |
| 真实 Apple 服务 | 完整句正常翻译；片段只保留词义 | 旧全量检查通过，bank两义及短语否定保留；新增片段API保留本机解释、sensor得到“传感器”，均无自动句译 | 本机通过；远程缺包时明确跳过 |
| 补采/状态/数据 | 最多一次，取消不应用旧结果，失败保留原文 | 注入式恢复、变词拒绝、取消、错误保留及负坐标边界通过；完整性缓存隔离、旧格式、收藏/最近记录读回通过 | 自动检查通过；不等同物理鼠标验收 |
| 实际卡片、Release、安装 | 片段标签和操作清楚，同身份升级 | 12类原生布局通过，[manifest](mac-layouts/manifest.json)及PNG已复核；源码2493b3b的Release及同身份安装build17/严格验签完成；CI42775293869成功 | 通过 |

真实识字图像由程序离屏绘制，不读取用户应用或真实词本，不启动桌面控制鼠标。示例：[完整跨行](vision/wrap-light-system.png)、[注释](vision/comments-dark-mono.png)、[两端裁切](vision/clipped-both-dark-mono.png)。布局截图采用固定的已声明释义，不算作模型准确性测试。

## 复现

在仓库根目录运行：

```sh
./scripts/check.sh
./scripts/check-card-layouts.sh /tmp/wax-sentence-layouts
swift build -c release -j 2
```

仅运行本专项：`./scripts/check-sentence-boundaries.sh`。可设置 `WAX_BOUNDARY_REPORT` 和 `WAX_BOUNDARY_IMAGES` 输出合成语料报告和真实 Vision 图像；没有真实用户内容。`WAX_BOUNDARY_BASELINE=1` 仅供在旧基线源代码上执行同语料对照，跳过旧版本不存在的字段/新运行时能力，不能用作新版本门禁。

此次共享 JSON 与两端测试必须保持同一版本。Windows 实际包、100%/150% 桌面检查、原生截图和源提交对应关系见下文及同一 Issue/PR，不以 Mac 结果代替。


## Windows 最终证据

Windows 11 x64 / Python3.12，使用实际便携包的应用模块和隔离测试数据，在独立runner显示窗口并执行真实输入，不占用用户桌面。Mac本机纯Python通过不是Windows原生证据。

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 同一契约与平台适配 | 两端范围/完整性一致，入口不丢元数据 | 实际包160/160；91个editor/OCR入口均通过 | [报告](windows-report.json)，通过 |
| 真实多行OCR与补采 | 两种OCR保留多行，疑似半句最多一次补采 | 原生/离线均读回完整三行并保留否定；两档实际屏幕均从局部扩展一次后读回完整七行，截图次数为2 | 桌面通过 |
| 取消/变词/失败 | 旧任务不回写，补采失败保留首次片段 | 后台取消、延迟捕获过期、变词拒绝、错误回退通过 | 注入式及实际桌面分别验证 |
| Provider与卡片 | 片段不自动句译，显式操作仅译当前范围 | 四态保留API解释且无自动句译；取消后旧句译不显示；片段听读标签正确；独立词不重复原文 | 通过 |
| 旧库升级与复习 | 旧字段和进度保留，片段不会变成完整句 | 合法旧格式、保存读回、due/streak不变、代码旧结构安全值、词本及复习片段标签通过 | 隔离数据通过，不替代真实历史用户库 |
| 实际包及全量桌面 | 包可启动，资源完整，两档流程一致 | [CI42780828105](https://github.com/wax0629/WaxTranslate/actions/runs/42780828105)：100%118/118（130.890秒），150%118/118（120.404秒），无跳过；EXE/重复激活/默认与可选包通过 | 通过 |
| 原生多语种OCR | 英日/韩/俄系统识字并与离线回退协作 | [CI42780828231](https://github.com/wax0629/WaxTranslate/actions/runs/42780828231)：真实截图2/2、识别路由16/16通过 | 通过 |
| 实际卡片与缩放 | 标签、操作和布局可读，不残留旧帧 | 两档before/after共80张；四种片段PNG逐图复核，381逻辑点宽，100%381像素/150%572像素 | [完整artifact](https://github.com/wax0629/WaxTranslate/actions/runs/42780828105/artifacts/13747075155)，通过 |

[便携试用包](https://github.com/wax0629/WaxTranslate/actions/runs/42780828105/artifacts/13746860612)对应已验证源`c298418`。`evidence.json`中的摘要是GitHub artifact整体摘要，不是内部ZIP单文件摘要。图像使用固定声明释义，只证明真实UI呈现；语义/OCR/模型验证由独立测试证明。

| 卡片 | 100% | 150% |
| --- | --- | --- |
| 缺首 | [截图](windows-layouts/scale-1/after/partial-missingStart.png) | [截图](windows-layouts/scale-1.5/after/partial-missingStart.png) |
| 缺尾 | [修改前](windows-layouts/scale-1/before/partial-missingEnd.png) / [修改后](windows-layouts/scale-1/after/partial-missingEnd.png) | [修改前](windows-layouts/scale-1.5/before/partial-missingEnd.png) / [修改后](windows-layouts/scale-1.5/after/partial-missingEnd.png) |
| 两端缺失 | [截图](windows-layouts/scale-1/after/partial-missingBoth.png) | [截图](windows-layouts/scale-1.5/after/partial-missingBoth.png) |
| 未确认完整 | [截图](windows-layouts/scale-1/after/partial-uncertain.png) | [截图](windows-layouts/scale-1.5/after/partial-uncertain.png) |
| 完整外语术语自动对照 | [截图](windows-layouts/scale-1/after/rules-foreign-term.png) | [截图](windows-layouts/scale-1.5/after/rules-foreign-term.png) |

仓库只归档上述直接截图与筛选manifest，完整80张和完整manifest在artifact；源版本及缩放均保留。基线不支持extent，原样呈现旧卡片，不给旧版本强加新字段。

首轮8de9828未通过：旧测试要求未完日语歌词自动句译、测试SQLite句柄漏关、基线截图脚本不兼容新extent参数。c298418保留歌词词义/显式框选，按新规则断言无自动句译；关闭测试连接并兼容旧基线后，完整两档与原生OCR重跑通过。失败未被计作验收成功，详情见#92。

Windows复现（隔离桌面）：

```powershell
python windows/test_sentence_boundaries.py --contract --report boundary-report.json
.\windows\setup.cmd
.\.venv\Scripts\python.exe windows\install_model.py --all-languages
$env:QT_SCALE_FACTOR='1'
.\.venv\Scripts\python.exe windows\check.py --desktop -v
$env:QT_SCALE_FACTOR='1.5'
.\.venv\Scripts\python.exe windows\check.py --desktop -v
```

`--contract`仅使用标准库，可在其他平台比较同语料；它不替代Windows包和原生检查。真实用户词本覆盖升级、人工声音/读屏、任意应用的全部物理手势仍由#1/#78/#79跟踪。
