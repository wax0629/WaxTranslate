# macOS 同步界面复核记录

2026-11-09 · [Issue #78](https://github.com/wax0629/WaxTranslate/issues/78)

本轮是在现有产品方向上补齐 Mac 操作界面。视觉依据为 [PRODUCT.md](../../../PRODUCT.md) 与 Windows [首页](../../../Assets/Previews/windows-home.png)、[取词卡](../../../Assets/Previews/windows-lookup.png)：沿用黑白漫画、暖纸色背景、英文阅读用 Baskerville 衬线字体、中文及控件用系统字体。未建立新视觉方向，未生成 `DESIGN.md` 或 `.impeccable/design.json`，既有图标及漫画资源保持原样。

用户最新约束是去掉所有页面顶部独立的系统边框。四页现共用整合顶栏；[App.swift](../../../Sources/waxtranlate/App.swift) 使用 `fullSizeContentView`、隐藏标题、透明标题栏与无标题栏分隔线，保留原生关闭、最小化、缩放及背景拖动。取词卡使用 `borderless` 浮窗，在卡内固定、关闭。

## 检查依据

代码检查覆盖 [DeskTheme.swift](../../../Sources/waxtranlate/DeskTheme.swift)、[Panels.swift](../../../Sources/waxtranlate/Panels.swift)、[Reading.swift](../../../Sources/waxtranlate/Reading.swift)、[ResultCard.swift](../../../Sources/waxtranlate/ResultCard.swift) 和上述窗口配置。

逐张查看了 `.impeccable/review/` 中的九张原生应用截图，并确认本目录归档与其逐文件 SHA-256 一致：

- 首页：[宽窗](home.png)、[窄窗](home-narrow.png)。
- 对照翻译：[宽窗](reading.png)、[窄窗顶部](reading-narrow.png)、[窄窗滚动到底部](reading-narrow-bottom.png)。
- 生词本：[宽窗](words.png)、[窄窗](words-narrow.png)。
- [设置](settings.png)、[取词卡](card.png)。

截图中四页均未见额外的系统标题条；阅读宽窗并排、窄窗上下排列，底部截图可见完整译文与状态。左上紫色图标是 macOS 屏幕共享覆盖层，会遮住原生窗口控制区域，不属于产品顶栏。

## 原评审两项修复

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 缺少持久化产品记录 | 已确认的用户流程、既有方向及最新窗口约束可供后续工作复用 | 根目录新增 `PRODUCT.md`，记录上述事实并指向 #78 及平台文档 | 已解决 |
| 生词本模式标签换行 | 模式切换不再额外显示挤占空间的「词本模式」标签 | `Picker("词本模式", …)` 增加 `.labelsHidden()`；保留「全部词条／到期复习」分段选项；重拍宽窄截图均无标签换行 | 已解决 |

原评审 disposition 为 `fix`；同一复核者在两项修复后判定均已解决，最终为 **`ship`，仅限上述两项修复**。该结论不扩大为全部 macOS 功能、所有窗口尺寸或完整发布流程均已验收。

## 证据边界

截图来自真实已安装应用，使用合成内容与隔离 UI 数据目录，说明对应运行状态下的排版；不能据此认定真实用户数据迁移、全局 OCR、翻译准确率、权限申请、键盘焦点及窗口拖动全部通过。功能、构建与签名验证另见[开发记录](../../development.md)。

本轮采用原生截图与 SwiftUI/AppKit 源码复核，无已批准的逐像素设计稿。CSS 检测器不支持该原生实现，未执行，也未将其记作通过；动态行为与辅助功能不由静态截图代替验证。既有上下文或设计资产未作额外修订，本记录不将未核验的历史差异确立为设计规范。
