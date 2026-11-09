# macOS 0.3.0 同步验收

后续用户反馈的默认 Option、Dock 设置、图标、两排布局、重复入口、简体输出和性能分段结果，见 [build 9 追加验收](followup.md)。本页原始截图保留其对应阶段，不代表最新布局。

中文语境中的名称/缩写解析、原样回退边界和卡片字号调整，见 [build 10 术语验收](terminology.md)。

2026-11-09，本机 macOS 26.6.2 / Intel，Swift 6.3.3，macOS SDK 26.5。开发与验收对应 [#78](https://github.com/wax0629/WaxTranslate/issues/78)，去掉独立系统标题栏对应 [#79](https://github.com/wax0629/WaxTranslate/issues/79)。以 main `f6f651c` 为基线，最终产品提交及远程 CI 链接在本轮 PR 正文记录。

## 本机自动化与真实服务

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| `./scripts/check.sh` | Vision、词条定位、短语、旧数据、复习和新增流程通过 | 真实 Vision、重复词精确位置、同栏换行、标点边界、词本迁移、跨日统计、最近六条、损坏数据保留、阅读取消/过期结果、本机术语和百科请求边界均通过 | 通过，本机自动化 |
| 紧排词的真实 OCR | docs 和 logistics、warehouse 和 parcel 各自命中 | 首次回归复现 logistics 被取成 docs；查明 Vision 返回相同联合词框后，使用共享框中的字形位置消歧。系统 20/32pt、Baskerville 24pt、等宽 24pt，分别检查五个落点，含第二次出现的 bank | 修复后 20 组通过；不是全字体准确率结论 |
| Apple 英中翻译 | 句中词义与原句保真 | 孤立及句中 tulip → 郁金香；bank → 岸边／银行；rule out → 排除且保留否定；ran out of → 用完了；look up → 查一下／仰望；故意失配的 memory 不取 ended 的「结束」；真实日中「猫が眠っています。」→「猫在睡觉。」 | 通过，真实本机服务 |
| `swift build -c release -j 2` / 安装脚本 | 生成并安装 0.3.0 | Release 构建、资源打包、安装及 `codesign --verify --strict` 通过 | 通过，本机真实运行 |
| 签名与权限 | 复用旧开发签名及授权 | bundle ID 仍为 local.luma.hovertranslate，签名要求与旧 0.2.3 相同；设置实际显示屏幕取词已授权 | 通过；未重新授予权限 |
| Windows 词表一致性 | Mac 数据不漂移 | `scripts/sync-reading-terms.py --check` 通过；API、MVP 开发/体育、Codex 编程/手稿、Rust 与普通 rust、文中 MAR 展开及临近词义反例通过 | 通过；没有声称全部 Windows 句式等价 |

共享词框的字形位置是几何估计。真实字体、低清画面、文字遮挡及系统识字仍可能造成偏差；没有将这 20 组回归外推为通用准确率。旧 macOS 未真机重测。

首轮远程 CI 在 Xcode 26.6 下复现了全新机器没有英汉词典时 tulip 仍被判为印尼语的问题；不能用本机已装词典的通过结果掩盖这一失败。修复后增加强制无词典证据的回归，同时核对 bonjour、gatto、hola、hallo、obrigado 和真正的印尼语 rumah，不将所有拉丁短词强制改成英语。本机完整回归、真实孤立/句中 tulip 及日中翻译已重跑通过；最终远程结果见 PR 正文。

## 安装版实际界面操作

以下操作在 `WaxTranslate.Test.*` 独立偏好域进行，不使用用户真实词本。首页六行图使用专门的合成夹具；其他图分别来自合成旧词条与实际 UI 查询、保存和复习产生的状态，不能将图中次数理解为真实用户历史。

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 四页顶部 | 无独立系统标题条，保留应用导航 | 首页、对照翻译、生词本、设置及取词卡均有真实运行截图；主窗整合原生控制，浮卡 borderless | 通过 |
| 宽窄窗口 | 导航完整，内容可读 | 正常 980pt 与约 562–572pt 宽度实际调整；阅读改为上下排列，可滚动读完译文；词本模式两选项不再折行 | 通过 |
| 全文翻译 | 真实样文获得译文 | 点「试读样文」「翻译全文」，读回三段中文，否定与内存耗尽含义保留 | 通过，真实 Apple 翻译 |
| 应用内查词及保存 | 从原文命中短语并保存语境 | 双击 out 后查询 rule out → 排除；统计由 0 增至 1；卡片固定/取消、展开原句及句译、复制反馈、加入生词本及 Esc 关闭均被实际操作；词本读回新词条及句译 | 通过；复制反馈已验，剪贴板读回因并行使用未独立确认 |
| 旧格式复习 | 同批旧格式条目可读并更新进度 | 预置 bank、warehouse 旧格式数据，显示 bank「河岸」，点击记住后切到 warehouse，待复习 3 → 2、已掌握 1 → 2；另有持久化重读自动回归 | 通过，合成旧格式及真实 UI；不等同真实用户历史升级 |
| 系统语言包 | 缺包可进入系统安装并刷新状态 | 实际打开 Apple 下载弹层，完成日语；韩语下载中返回设置显示未完成提示，后台完成后重新进入设置显示已安装。最终英、日、韩、中均显示已安装 | 通过，真实系统流程；未测其余六种语言的真实下载/译文质量 |
| 跨应用全局快捷键 | 从 TextEdit 指向单词触发取词 | 使用专用 RTF 样文尝试，自动化按键向文本窗口插入了字符，未确认全局事件派发；已撤销并关闭样文 | 未完成真机手动验收；不记作取词通过 |
| 框选与窗口系统操作 | 框选、Esc、最小化、缩放、关闭/唤回可用 | 保留生产入口、原生控制及选区处理；本轮实际验证窗口调整尺寸和卡片 Esc，未用当前工具完成全部桌面手势组合 | 其余组合待人工复核 |
| 朗读与 VoiceOver | 发音与辅助操作正确 | 入口保留；没有人工听验声音或完整 VoiceOver 走查 | 未执行人工验收 |

## 升级边界

升级前已备份本机 0.2.3 应用及偏好域到 `~/Library/Application Support/waxtranlate/UpgradeBackups/`，没有将签名材料或用户数据提交到仓库。当前用户词本原本没有历史条目；因此 [#1](https://github.com/wax0629/WaxTranslate/issues/1) 的「带真实历史词条的正式包覆盖升级」仍未完成。本轮验证的是开发版安装、签名一致、既有授权及合成旧格式读写，不能代替该项正式验收。

远程 macOS CI 执行同一检查与 Release 构建；未安装英中包时会明确跳过真实 Apple 翻译，不据此推断真实服务通过。当前 PR head 的 CI 结论在 PR 正文记录。Windows 产品代码没有修改，本轮没有重新执行 Windows 桌面回归。

## 截图

更新前：[0.2.3 实际首页](before.png)。下列均为安装版真实窗口；六行首页由合成测试夹具提供数据，不是产品内置示例。左上紫色控件属于 macOS 屏幕共享状态。

| 页面 | 正常窗口 | 窄窗口 |
| --- | --- | --- |
| 首页 | [六行夹具](home.png) | [窄窗](home-narrow.png) |
| 对照翻译 | [真实英中译文](reading.png) | [顶部](reading-narrow.png) · [滚动至译文底部](reading-narrow-bottom.png) |
| 生词本 | [旧格式词条](words.png) | [窄窗](words-narrow.png) |
| 设置 | [英日韩中已安装](settings.png) | 本轮未单独归档 |
| 取词卡 | [rule out](card.png) | 紧凑浮窗 |

[Apple 下载弹层](language-download.png) · [实际复习后的首页](home-after-review.png) · [独立设计检查及修复记录](design-review.md)

## 复现

```sh
./scripts/check.sh
swift build -c release -j 2
./scripts/install.sh
python3 scripts/prepare-ui-profile.py --profile WaxTranslate.Test.manual-check --scenario full
open "$HOME/Applications/waxtranlate.app" --args --test-profile WaxTranslate.Test.manual-check --show
```

先退出已有实例再使用专用测试参数；已运行的应用不会接收后续 `open --args` 参数。支持 empty、legacy、full 三种夹具。退出测试实例后，仅删除对应的专用域：`defaults delete WaxTranslate.Test.manual-check`，然后正常打开应用。不得删除真实偏好域。

跨应用人工验收可用 `open -a TextEdit Tests/Fixtures/hover-sample.rtf`，分别指向 docs、logistics、斜杠两侧、第二个 bank 及两组短语，使用实际键盘触发 ⌥⇧T，再执行框选、Esc 取消和窗口最小化/唤回。该 RTF 只含合成样文。
