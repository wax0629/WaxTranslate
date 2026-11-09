# WaxTranslate · 我靠翻译

在网页、PDF 或其他应用里读外文时，把鼠标指向生词，按一下快捷键，就能看它在原句里的意思。比如同一个 `bank`，读河边的故事时可以查到「岸边」，读存款的例句时可以查到「银行」。也可以框选整段翻译，或把词和原句一起存进生词本复习。

| 开发版 | 查鼠标下的词 | 翻译一段 |
| --- | --- | --- |
| Windows 11 x64 | 轻按并松开左 Ctrl | 按住取词键，用鼠标左键拖选 |
| macOS 15.2 及以上 | ⌥⇧T（Option + Shift + T） | 按 ⌥⇧R 后拖选 |

## 当前开发进度

截至 2026-11-09，Windows 和 macOS 均有可运行的开发版。Windows 支持九种原文语言离线中译、对照阅读、生词复习和查词看板，界面已按 Mac 开发版统一。取词卡区分名称、普通词和未知标识，中文混排可点词、按需翻译原文。macOS 主分支版本为 0.2.2，后续阅读学习与语境卡片仍在独立 PR 中验证。[开发进度与验收记录](docs/development.md) · [双端路线图](https://github.com/wax0629/WaxTranslate/issues/3)

Windows 的两档缩放、真实便携包及多语 OCR 验收与下载入口见 [Windows 交付记录 #86](https://github.com/wax0629/WaxTranslate/issues/86)。[语境卡片验收样例](docs/verification/windows-card-rules/README.md)记录实际词义、原文边界、取消与收藏规则。

## WaxTranslate Windows 桌面版

**使用便携包。** 登录 GitHub，从 Windows 交付记录打开最终通过的桌面构建，在运行页底部的 Artifacts 下载 `WaxTranslate-Windows-x64`。解开下载文件，再完整解开其中的便携 ZIP，双击 `WaxTranslate.exe`。程序默认在系统托盘待命；点击托盘图标或再次双击启动器可打开首页。[验收及下载记录](https://github.com/wax0629/WaxTranslate/issues/86) · [Windows 构建列表](https://github.com/wax0629/WaxTranslate/actions/workflows/windows-desktop.yml)

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
open "$HOME/Applications/waxtranlate.app"
```

1. 在「系统设置 → 隐私与安全性 → 屏幕与系统音频录制」允许「我靠翻译」，按系统提示重新打开。首页会显示当前授权状态。
2. 将鼠标指向原文按 **⌥⇧T**，或按 **⌥⇧R** 后拖选一段文字。应用用 Vision 在本机识字，使用 Apple 翻译。需要语言包时可从结果卡片下载。中文译为英文，其余系统支持的原文语言译为简体中文。
3. 在结果卡片上朗读、复制或收藏。要复习时，从菜单栏的书本图标打开主窗口，切到「复习」。

安装脚本会退出正在运行的旧版、复用签名并保留生词本。请保留 `~/Library/Application Support/waxtranlate/BuildSigning` 中的签名材料。从旧版临时签名升级后，如果仍显示未授权，请在「屏幕与系统音频录制」中移除旧条目，重新添加当前应用并重启。正式安装包覆盖已有真实生词记录的验收仍在跟踪。[macOS 升级记录](https://github.com/wax0629/WaxTranslate/issues/1)

## 验证

Windows 的离屏回归、独立桌面回归、多语 OCR 专项，以及 macOS 的 Vision 和 Apple 翻译检查，均有对应命令和运行条件。[复现验证](docs/development.md#复现验证)
