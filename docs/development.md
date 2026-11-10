# 开发进度与验收记录

截至 **2026-11-10**，Windows 视觉 #82 与语境卡片 #87 已依次集成；Mac 阅读学习、窗口和常用设置由 #80 接续集成。查询决策和卡片规则的后续实现见 Mac #85、Windows #89。Windows 提供实际验收的便携构建，macOS 提供源码安装脚本。[双端路线图](https://github.com/wax0629/WaxTranslate/issues/3)

## 当前准入结论

本次交付用于开发版有限试用。Windows 当前语境卡片的 107 项实际包桌面回归及多语 OCR 依据见 [#86](https://github.com/wax0629/WaxTranslate/issues/86)；Mac build12 的真实 Vision、Apple 翻译、安装及界面证据见 [同步验收](verification/macos-sync/README.md)。新的 #85/#89 各自记录新规则验证，不能把旧构建结果当作新提交的验收。真实历史词本升级、人工听感/读屏和全部第三方应用的物理交互仍保留待验收。

## macOS 0.3.0 同步交付（2026-11-09）

[Issue #78](https://github.com/wax0629/WaxTranslate/issues/78) 在 `f6f651c` 上承接 #4 / #6 的短语修复，补齐首页四格统计及最近六条、对照阅读、紧凑取词卡、生词复习、源语言和快捷键设置、系统语言包及登录项入口。Windows 缩写/名称词表生成 Mac 资源；语境消歧、文中定义和百科查询保留来源与边界。旧个人签名 PR #7 不覆盖主分支后续采用的品牌图标。

本轮追加修订：菜单栏改用已确认的漫画图标，显式设置运行时应用图标；首页统计按用户最新决定固定两排两列，限制卡片宽度；新配置默认轻按 Option 取词，保留已有组合键选择；设置新增可持久化且即时生效的 Dock 显示开关。对应验证见 [追加验收](verification/macos-sync/followup.md)。

本机 macOS 26.6.2 / Intel，Swift 6.3.3 / SDK 26.5 的真实 Vision、Apple 英中翻译、旧词本、统计、过期结果与术语回归通过；Release 构建通过。应用保持原 bundle ID、词本键和签名身份。真实历史词本仍不能据空数据升级勾选；本机升级前词本为空，已有旧应用及偏好域备份。详细证据、截图、待验证范围与复现入口见 [本轮 Mac 验收](verification/macos-sync/README.md) 和 [Mac 指南](macos.md)。连续短语 #6 的功能已在当前集成实现中验证，不重新合入旧分支。

## 已进入主分支

| 平台 | 已交付的用户操作 | 交付依据 |
| --- | --- | --- |
| Windows · 取词与学习 | 从托盘轻按取词、拖动框选。在对照页粘贴文章，听读、保存和复习。首页固定展示四项学习统计及最多六条最近取词，取词卡可固定、展开和复制。 | [便携版与生词本 #18](https://github.com/wax0629/WaxTranslate/pull/18) · [阅读与听读 #30](https://github.com/wax0629/WaxTranslate/pull/30) · [看板和取词卡 #71](https://github.com/wax0629/WaxTranslate/pull/71) |
| Windows · 语言与识字 | 默认英、日、韩，法、德、西、意、葡、俄按需安装，九种均可离线译为简体中文。悬停按命中行判断，框选可译整行歌名。支持切换取词键、仅应用内查词，以及单独长按 Ctrl 后松开而不触发。 | [语言包 #59](https://github.com/wax0629/WaxTranslate/pull/59) · [长按手势 #70](https://github.com/wax0629/WaxTranslate/issues/70) · [多语种 OCR #73](https://github.com/wax0629/WaxTranslate/pull/73) |
| Windows · 界面与语境卡片 | 首页、阅读、词本、设置和取词卡采用统一纸色与字体层级。名称、普通词和未知标识分别展示；中文混排保留短原文，点词和句译均保留具体位置与边界。未知结果禁收藏，百科由用户主动发起。词头和原文分别选择朗读语种，旧词本与复习计划兼容。 | [视觉同步 #82](https://github.com/wax0629/WaxTranslate/pull/82) · [卡片规则 #87](https://github.com/wax0629/WaxTranslate/pull/87) · [验收样例](verification/windows-card-rules/README.md) |
| macOS · 取词、阅读与复习 | 0.3.0 build12：默认 Option 取词、框选、对照阅读、生词与到期复习；首页两排统计与最近查询。四页整合顶栏，设置控制 Dock、快捷键及系统语言包。Vision 与 Apple 翻译路线保留。 | [同步 #80](https://github.com/wax0629/WaxTranslate/pull/80) · [Mac 验收](verification/macos-sync/README.md) · [升级验证 #1](https://github.com/wax0629/WaxTranslate/issues/1) |

## 最近一次 Windows 验收

本轮在独立 Windows runner 中对实际便携包检查启动、重复激活、默认与可选语言包、100%／150% 桌面交互及原生截图；另有英、日、韩、俄原生 OCR 专项。完整检查现覆盖 107 项，包含新增九项语境规则验收。每次运行的终态和提交对应关系记在 [#87](https://github.com/wax0629/WaxTranslate/pull/87)，截图含实际尺寸、倍率及卡片文字与收藏状态，避免把旧帧当成新结果。

本机 Windows 11 的离屏回归覆盖真实模型与 OCR，桌面操作在独立 runner 执行。新增语义样例实际区分 bank 的河岸／银行、VoiceOver 与 voice-over、README、INTEGER、重复 token 和未知代码；同时检查标题整译、注释与列表边界、按需句译取消以及收藏读回。人工听感、屏幕阅读器操作和任意第三方应用的物理手势仍不是这些自动检查的结论。[本轮验证与范围](verification/windows-card-rules/README.md)

下表保留 #73 合并前的历史实测，不作为最新卡片代码的验收依据。缩放比例是桌面回归设置；OCR 样本的组合数另行统计。

| 环境 | 操作与结果 |
| --- | --- |
| 独立 Windows 桌面 | 从 ZIP 解压并启动便携版，用真实鼠标和快捷键走完悬停、框选及关闭。在 100% 与 150% Qt 缩放下各通过 **93/93** 项。[桌面运行记录](https://github.com/wax0629/WaxTranslate/actions/runs/42459577744) |
| 独立 Windows 多语种环境 | 安装英、日、韩、俄四种原生 OCR。屏幕取词与框选检查 **2/2** 通过，语种识别专项 **16/16** 通过。[多语种运行记录](https://github.com/wax0629/WaxTranslate/actions/runs/42459577742) |
| 本机离屏与原截图 | 两档缩放各通过 90 项，3 项真实桌面专用检查在独立桌面运行。用解压包重查网易云截图，悬停分别命中 `conjoined`、`interlude`，框选读回完整标题，三次均得到中文译文。[复测记录 #72](https://github.com/wax0629/WaxTranslate/issues/72) |

英文专项以 23 个样本覆盖单字母、长词、缩写、数字、标点和重复词。每个样本在「悬停／框选」与「系统 OCR 可用／仅离线包」的四种组合下核对，合计 92 组。另有深浅底、低对比、重采样、日韩俄短标题、多语混排和指定源语言的用例。单独的竖笔画仍可能在 `I`、`l` 或符号间混淆，自动模式可在证据不足时提示重新框选。[回归样本与断言](../windows/test_ocr_routing.py)

## 待合并与待验收

| 工作 | 当前进度与验收条件 |
| --- | --- |
| macOS 英语连续短语 | 原 PR #6 的已验收实现由本轮 #78 集成至最新主分支基线；本轮真实 Apple 翻译回归通过，已由 #80 接续集成。[功能记录 #4](https://github.com/wax0629/WaxTranslate/issues/4) · [安装版对照 #6](https://github.com/wax0629/WaxTranslate/pull/6) |
| macOS 孤立词语种判断 | 本轮 #78 以本机英语词典证据改进孤立词判断，并提供明确源语言选项。`tulip`、完整非英语句子及手动覆盖回归通过，已由 #80 接续集成。[问题 #2](https://github.com/wax0629/WaxTranslate/issues/2) |
| macOS 正式包升级 | 开发版和旧数据格式已有验证，正式安装包仍需在带有真实历史词条的旧版上覆盖安装，并核对升级后的记录。[验收清单 #1](https://github.com/wax0629/WaxTranslate/issues/1) |
| 双端一致性 | 待用同一组样文在两端对照取词、框选、取消和关闭，并核对默认与放大显示下的排版。语境准确性仍需人工对照多义词、术语、否定和跨行文本。[路线图 #3](https://github.com/wax0629/WaxTranslate/issues/3) |

macOS 15.2 为最低运行版本。macOS 26.4 及以上可尝试从整句译文中对齐命中词，对齐失败时显示独立参考释义。OCR 只能拼接取景范围内可见的原句，遮挡、分栏和系统译词都会影响结果。已有验收记录提到 `emergent capabilities` 的术语误译，仍需结合语境复核。[主分支翻译实现](../Sources/waxtranlate/LookupTranslation.swift) · [验收目标](https://github.com/wax0629/WaxTranslate/issues/3)

## 复现验证

### Windows

在仓库根目录运行。首次需要带 `py` 启动器的 Python 3.12 x64；完整回归要安装可选语言包。日常检查默认离屏，不占用当前桌面的鼠标和键盘。

```powershell
.\windows\setup.cmd
.\.venv\Scripts\python.exe windows\install_model.py --all-languages
.\.venv\Scripts\python.exe windows\check.py -v
```

只复查语种误判时，运行 `.\.venv\Scripts\python.exe windows\check.py -v -k test_ocr_routing`。复现真实手势使用 `.\.venv\Scripts\python.exe windows\check.py --desktop -v`，会显示窗口、移动光标并发送按键。优先在独立 runner 或空闲测试桌面运行，并退出同样监听取词手势的程序。[桌面工作流](../.github/workflows/windows-desktop.yml) · [原生 OCR 工作流](../.github/workflows/windows-ocr.yml)

本地构建便携 ZIP：

```powershell
.\.venv\Scripts\python.exe windows\package.py dist\WaxTranslate-Windows-x64.zip
```

### macOS

在装有 Swift 6 和 macOS 26.4 或更新 SDK 的 Mac 上，运行 `./scripts/check.sh` 和 `swift build -c release`。脚本覆盖 Vision 双栏跨行识字、屏幕边缘、重复词的命中位置、旧格式生词及复习记录。在系统支持并已安装英中翻译包时，还会检查 `bank` 在河边和存款两种语境中的真实译义。Mac 验收记录来自对应 Issue、PR 与本机真实服务检查。[检查脚本](../scripts/check.sh) · [测试样例](../Tests/waxtranlateTests/ReaderTests.swift)
