# 点到 study 后出现什么

在「对照翻译」打开试读样文，双击第一句里的 `study`。卡片标题应为 `ablation study`，中文释义是「消融实验」，英语原句加粗这两个词。再双击 `housing`，点「调整范围 → 包含左词 · battery housing」就能用同一句话查「电池外壳」。英文样文在两个平台都可使用。Windows 的试读示例先打开原有的 `bank` 卡片，关闭后可在编辑器里双击其他词。

| 旧版 | 本轮开发版 |
| --- | --- |
| ![旧版只选中 study，词头释义是研究](before.png) | ![新版选中 ablation study，先读消融实验，再对照原句](after.png) |

## Mac 实测

本机为 Intel Mac、macOS 26.6.2，已安装 Apple 英译中语言包。测试绘制固定英文原句，向真实 Vision 提供同样的像素与落点，装载正式的 SwiftUI 浮窗，在卡片已有首个解释、完成布局后读表。每次先按应用方式预热 Vision 和翻译，首次查询无已识别画面或词义缓存。旧版与新版各启动三次，每个进程连续查三次，运行顺序为旧、新、新、旧、旧、新。计时包含 OCR、范围识别、释义与卡片布局，8 毫秒轮询；使用离屏窗口和合成输入，不包含物理按键、屏幕录制授权或第一次下载语言包。

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 首次出现的解释 | 首张卡直接回答整组在这里的含义 | 旧版 9 次都是「研究」，新版 9 次都是「消融实验」并附中文解释 | 此样例通过 |
| 首查响应 | 分开记录首次与重复查询，比较相同输入 | 首次中位数由 3448 毫秒到 2480 毫秒，各 3 次。旧版的计时终点为单词「研究」 | 单机样例，首查仍有可感知等待 |
| 相同画面重复查 | 记录可读释义的延迟 | 中位数由 134 毫秒到 104 毫秒，各 6 次 | 此样例通过 |
| 实际本地模型 | 手动扩词保留词义，否定句保留否定 | `battery housing` 得到「电池外壳」。`The model did not show emergent capabilities.` 得到「该模型没有显示涌现能力。」 | Apple 本机运行通过 |
| 选择与边界 | 同一拼写按邻近语境判断，重复词按位置识别 | 医疗消融、逗号隔开的单词、不同分句、最长术语和重复词均通过。点击收藏后晚到的句译补入原条目 | 自动回归通过 |

已有词表覆盖九组术语及单复数等形式，来自机器学习、统计与并发编程。显式扩大选区可用于其他英文搭配。术语和释义可在两端离线使用。两端句译分别由系统翻译和本地模型生成，用词可能有差异。术语解释参考 [Google 机器学习术语表](https://developers.google.com/machine-learning/glossary#ablation)及[涌现能力论文](https://arxiv.org/abs/2206.07682)。

## 复现

```sh
./scripts/check.sh
./scripts/check-hover-feedback.sh --phrase-preview dist/phrase-review 801112838f7cc1bf29f962251c5ee628eb16fcc3
./scripts/check-card-layouts.sh dist/phrase-review/layouts
python3 scripts/windows_regression.py check
```

Windows 的隔离 CI 会构建实际便携包，执行桌面回归，并在 100% 和 150% 缩放各保留一套 `phrase-study.png` 前后截图。当前提交的 CI 与安装入口见 [Issue #108](https://github.com/wax0629/WaxTranslate/issues/108)。
