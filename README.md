# WaxTranslate · 我靠翻译

在网页、PDF 或其他应用里读外文时，把鼠标指向生词，按一下快捷键，就能看它在原句里的意思。比如同一个 `bank`，读河边的故事时可以查到「岸边」，读存款的例句时可以查到「银行」。也可以框选整段翻译，或把词和原句一起存进生词本复习。

| 开发版 | 查鼠标下的词 | 翻译一段 |
| --- | --- | --- |
| Windows 11 x64 | 轻按并松开左 Ctrl | 按住取词键，用鼠标左键拖选 |
| macOS 15.2 及以上 | 轻按并松开 Option | 按 ⌥⇧R 后拖选 |

## 试用状态（2026-11-10）

本轮换行、断句与半句处理已完成双端验收：Mac **0.3.0 build17** 已同身份安装并验签，160项共享契约、22项真实Vision、12类原生卡片布局、真实Apple服务与Release通过；Mac当前提交CI成功后才开始Windows同步。

Windows同一共享契约160/160，实际便携包在100%／150%下各 **118/118** 项桌面检查通过，多语种原生OCR **2+16** 项通过；四种片段卡片和缩放截图已复核。[当前试用包](https://github.com/wax0629/WaxTranslate/actions/runs/42780828105/artifacts/13746860612) · [验收报告与直接截图](docs/verification/sentence-boundaries/README.md) · [本轮交付与合并状态 #90](https://github.com/wax0629/WaxTranslate/issues/90)

完整外语句中的普通词和专业术语自动显示同范围原文与译文，中文语境点击才句译。跨行先区分段落、列表、标题、代码和注释，疑似裁切最多补采一次；仍不完整时明确显示片段，不补造原文。任意第三方应用的全部物理手势、人工听感/读屏和真实历史词本升级继续独立跟踪。[当前翻译逻辑](docs/translation-logic.md)

## 当前开发进度

双端支持对照阅读、生词复习、真实统计与最近查询，采用统一纸色、字体层级与简洁卡片。**外语自然句中的普通词和已确认术语/名称自动显示适长原文与对应译文；中文语境中的英文词由用户点击才句译。** 原文内其他术语按确切位置点击，注释去掉行首 // 且不接相邻代码，标题提供整译，路径/片段与未知名称保留边界。[翻译逻辑图](docs/translation-logic.md) · [开发与验收记录](docs/development.md)

Mac 使用 Vision 和 Apple 本机翻译，Windows 使用本地 OCR 和离线模型，语言包分别管理；两端不要求译文逐字一致。

## WaxTranslate Windows 桌面版

**使用便携包。** 登录 GitHub，从最新句译规则的交付记录打开最终通过的桌面构建，在运行页底部的 Artifacts 下载 `WaxTranslate-Windows-x64`。解开下载文件，再完整解开其中的便携 ZIP，双击 `WaxTranslate.exe`。程序默认在系统托盘待命；点击托盘图标或再次双击启动器可打开首页。[最新验收及下载记录](https://github.com/wax0629/WaxTranslate/pull/89) · [Windows 构建列表](https://github.com/wax0629/WaxTranslate/actions/workflows/windows-desktop.yml)

- **查词与框选**　轻按左 Ctrl 查一个词，或从顶部应用菜单、托盘菜单进入「框选翻译」。游戏占用左 Ctrl 时，可以在「设置 → 屏幕取词键」改用右 Ctrl，或选「仅应用内查词」。
- **语言包**　英语、日语、韩语随包提供。法语、德语、西班牙语、意大利语、葡萄牙语和俄语可在「设置 → 语言包」下载，安装后即可离线使用。
- **阅读与复习**　在「对照翻译」粘贴文章，点词看释义，按 Ctrl+Enter 看整段译文。在取词卡上点「加入我的生词本」，以后可以按原句复习。[Windows 使用指南](docs/windows.md)

### 从源码运行

在 Windows 11 x64 安装带 `py` 启动器的 Python 3.12 x64，然后在仓库根目录运行。首次安装需要联网下载依赖和默认模型。

```powershell
.\windows\setup.cmd
.\windows\start.cmd
```

## macOS 安装和运行

在装有 Swift 6 和 macOS 26.4 或更新 SDK 的 Mac 上，从仓库根目录构建安装。应用显示名为「我靠翻译」，磁盘文件名沿用 `waxtranlate.app`。

```sh
./scripts/install.sh
open "$HOME/Applications/waxtranlate.app" --args --show
```

1. 在「设置 → 屏幕取词」查看权限；跨应用取词需在系统设置的「屏幕与系统音频录制」中允许「我靠翻译」，按系统提示重新打开。
2. 指向原文，轻按并松开 **Option** 查词，或按 **⌥⇧R** 后拖选；Esc 取消。组合键输入、拖动或长按 Option 不触发查词。可改为 ⌥⇧T / R、⌃⌥T / R 或仅应用内模式，保留已有显式选择。连续 `rule out`、`run out of`、`look up` 按整组解释。
3. 在「对照翻译」粘贴文章，双击原文查词，点「翻译全文」或按 ⌘Enter 翻译。卡片可听读、固定、展开语境、复制和收藏。
4. 首页查看实际取词统计及最近六条；在「生词本 → 到期复习」复习收藏。设置可选择源语言、下载 Apple 语言包、控制「在 Dock 中显示」。默认在菜单栏待命。[Mac 使用与开发指南](docs/macos.md)

安装脚本会退出正在运行的旧版、复用签名并保留生词本。请保留 `~/Library/Application Support/waxtranlate/BuildSigning` 中的签名材料。从旧版临时签名升级后，如果仍显示未授权，请在「屏幕与系统音频录制」中移除旧条目，重新添加当前应用并重启。正式安装包覆盖已有真实生词记录的验收仍在跟踪。[macOS 升级记录](https://github.com/wax0629/WaxTranslate/issues/1)

## 验证

Windows 的离屏回归、独立桌面回归、多语 OCR 专项，以及 macOS 的 Vision 和 Apple 翻译检查，均有对应命令和运行条件。[复现验证](docs/development.md#复现验证)

当前句译触发规则见 [翻译逻辑](docs/translation-logic.md)。
