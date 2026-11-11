# 公开试用问题修复：本地预览

2026-11-11，基于 main `7b6897ff4714611833e2de692f15d8a39f1aa3fe`。负责人 Codex，[Issue #102](https://github.com/wax0629/WaxTranslate/issues/102)，接续 [#101 核查](../public-trial-2026-11-11.md)。本轮修复七项问题并补回归。以下为提交前的本机验收记录，分支、PR 与后续 CI 状态在 Issue 正文持续更新。

## 修复内容

| 问题 | 现在的行为 | 对应回归 |
| --- | --- | --- |
| Mac 框选自动留存原文 | 框选和整标题翻译不自动写最近取词或统计；主动收藏仍可保存并重启读回。历史数据沿用原格式。 | `ReaderTests.testRegionIsOnlySavedExplicitly`：无收藏时不写活动键；查词正常计数；框选收藏、去重、重载。 |
| Windows 托盘打不开阅读页 | 进入阅读页时显示、还原并激活主窗，保留输入且将焦点放到编辑器。 | `SettingsTests.test_tray_reader_opens_hidden_and_minimized_window`：启动到托盘、关闭到托盘、最小化三个入口。 |
| Windows 中文专名改变英语句译方向 | 按周围句子的离线语种证据判断；`Beijing` 换成 `北京` 或 `上海` 不关闭英语自动句译。中文含英文标识仍手动中译英，日/韩保持各自方向。 | `ContextLanguageTests` 三项及实际 `Window.translate_card_context` 的方向选择回归。 |
| Mac 长句词义误回退为银行 | 对齐失败后在完整原句上补充位置恢复；名词中心词保留完整中文词边界，至少两种标记一致才采用结果。成功后正常显示、收藏与缓存，证据不足保留未确认。临时词典参考和未确认结果不能进入语境收藏、最近记录或缓存。原句及节选译文保留。 | `LongContextTests` 和 `testContextAlignmentFailures`：固定输出重放、重复 bank、名词边界、否定/条件、失败、取消、旧 API、收藏和缓存；真实 Apple 16 个样本及无属性接口通过。 |
| Windows 损坏包不能修复 | 新装/打包资源带逐文件 SHA-256 清单，OCR 按固定摘要检查；修改文件会使校验缓存失效。旧包缺清单时由实际模型读取器验证。设置提供「修复语言包」，修复写入用户目录并优先使用；失败/取消保留旧模型，目录发布失败回滚；下一次翻译重载修复后的模型。 | `ModelIntegrityTests` 九项、设置下载/重试/修复回归、`TranslationResourceTests` 的真实旧包及常驻引擎回归。 |
| Mac 自动百科开关无效 | 移除无效开关，说明统一为点击地球按钮后查询；旧偏好键保留但不触发联网。 | 原生卡片挂载两种旧偏好均零请求；拦截 HTTP 验证仅当前词、断网重试、非 200 拒绝。 |
| Mac 关闭授权提示后取词静默 | 每次缺权限触发都替换为可恢复的授权提示，旧面板卸载，避免叠加。 | 实际 App 面板路径注入权限状态，验证首次拒绝、关闭重试、连续重入、授权恢复、再次撤权。 |

长句点词已继续完成恢复修订：本机 16 个真实查询与 1 个无属性接口查询通过，固定长河岸句实际返回「河岸」，同句两个 bank 分别为银行和河岸。最新方法、截图和独立预览见[长句点词修复](../long-context/README.md)。下表其余验证保留分平台边界。

## 本地查看

- [项目 README 和双端截图](../../../README.md)。上一轮文档和四张图已拷入本修复树，原 `101-public-trial` 工作树保留。
- 最新 Mac 独立预览：本工作树的 `dist/local-review-102-long/WaxTranslate Preview.app`；前一版本仍在 `dist/local-review-102/`。双击启动；首次使用独立预览词本和偏好，默认仅应用内查词。可在对照翻译页粘贴下列样句并双击 bank；不会覆盖已安装应用。
- [原生长句卡片](mac-long-bank.png) · [原生框选卡片](mac-region.png)。图片由真实 Apple 输出和当前原生视图生成，使用隔离样例数据。

```text
They sat on the river bank and watched the water.
She deposited her paycheck at the bank.
After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains.
```

Windows 复验时，从托盘三种状态打开阅读页；用 `The API returns a label named 北京.` 和 `调用 API 查询北京。` 比较自动/手动句译；在设置选已安装语言，再点「修复语言包」。修复测试只在临时资源副本中破坏文件。

## 验证结果

环境：macOS 26.6.2 Intel、Swift 6.3.3、SDK 26.5、Python 3.12.13。验证时使用未提交的固定源码，因此以下证据对应本工作树及摘要；后续远程检查在 Issue 正文另记。

| 验证项 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| `./scripts/check.sh` | 原有与新增 Mac 回归、共享断句、原生权限及百科检查通过 | 160/160 断句、22 项真实 Vision、实际 EN/ZH 与 JA/ZH、长句 16+1 真实查询与确定性恢复；原生权限、百科、未确认卡片不留存和已确认卡片正常记录均通过 | 通过 |
| `./scripts/check-card-layouts.sh` | 12 类真实原生视图无尺寸异常 | 12/12 原生离屏布局通过 | 通过 |
| `swift build -c release -j 2` | 固定源码完成 Release | 最新长句修复 119.11 秒完成；独立预览包严格验签通过 | 通过 |
| Windows 可移植规则/资源/设置 | 混排 3 项、完整性/取消/回滚 9 项、设置下载与主动修复 2 项通过 | 14/14；离线检测器、真实文件系统和 Qt 设置控件，下载用隔离小型包替身 | 通过本机测试 |
| Windows 实际窗口及引擎 | 托盘、手动译向、资源修复后重载三项通过 | 3/3；Mac Qt 6.12 离屏执行实际窗口类，Windows OCR/注册表/边框及模型构造用替身 | 通过模拟依赖的 Qt 测试 |
| 真实旧模型 | 无清单的旧包仍可读取，截短后不可用且原包保留 | 真实西班牙语包：缺清单可加载、截短拒绝、原包保留；实际离线 `El gato duerme.` → `The cat sleeps.` | 通过本机兼容测试 |
| 原词本/共享语料 | 原有统计和迁移不退化 | Python 词本 7/7，断句契约 160/160 | 通过 |
| Windows 目录工具 | JSON/CSV 和自动入口一致 | 61 条用例，137 个方法；目录工具单测 13/13 | 通过 |
| Windows 原生候选包 | 新代码在 100%/150%、实际 Win32 文件占用等环境通过 | 本轮未构建或运行原生 Windows 包；测试已接入 `windows/check.py` 的自动发现与回归目录 | 未执行 |
| 最低 Mac 系统及物理权限 | macOS 15.2、真实拒绝/重授屏幕权限、第三方应用手势通过 | 旧 API 和授权状态有注入回归；未改变真实权限或进行最低系统实机操作 | 未执行 |

旧包补充验证使用 CTranslate2 4.8.5 / SentencePiece 0.2.1；本机试装 0.2.3 时源码构建缺少 pybind11 头而失败，改用官方 Mac wheel。项目锁定的 Windows 0.2.3 依赖保持原样，仍待原生验证。旧包使用实际模型读取器验证，文件结构和兼容性参见 [CTranslate2 官方说明](https://opennmt.net/CTranslate2/conversion.html)。

旧 `cc948d5` 的 Windows 120/120 CI 仅为历史基线，不证明本次修复。当前完整目录为 137 个测试方法，不等于本机跑过 137 项。源码与截图摘要、各层测试范围见 [validation.json](validation.json)。本地原始日志：上一轮在 `dist/local-review-102/evidence/`，本轮长句与重新执行的 Mac 检查在 `dist/local-review-102-long/evidence/`。

## 复跑命令

Mac：

```sh
./scripts/check.sh
./scripts/check-card-layouts.sh
swift build -c release -j 2
./scripts/capture-trial-fixes.sh
```

已准备语言包的 Windows 独立测试环境：

```powershell
.\.venv\Scripts\python.exe scripts\windows_regression.py check
.\.venv\Scripts\python.exe scripts\windows_regression.py run --case WT-WIN-009 --case WT-LOOK-009 --case WT-LANG-008
.\.venv\Scripts\python.exe windows\check.py -v
```

全桌面回归使用独立 Windows runner，命令为 `.\.venv\Scripts\python.exe windows\check.py --desktop -v`。真实用户电脑的桌面操作仍需提前说明影响并得到同意。
