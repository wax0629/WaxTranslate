# Windows 回归测试集

本目录把用户操作、固定输入、可检查的预期和现有自动检查集中起来。应用入口、模型及测试实现沿用仓库现有代码。

- [用例表 cases.csv](cases.csv)：UTF-8 BOM，可用Excel打开；包含步骤、预期、命中位置及自动入口。
- [机器可读目录](../../../Tests/Fixtures/windows-regression.json)：唯一编辑来源，共58条用例、八个模块。
- [共享断句语料](../../../Tests/Fixtures/sentence-boundaries.json)：直接引用91个基础场景及其160项变换检查，保留各自编号，不复制数据。

58条用户用例与120个unittest方法不是同一计数。一个方法可能覆盖多条样文；多个目录项也可能复用同一检查。按组执行会去重自动入口，`--full`运行现有全部检查。

## 执行层

| 层 | 本目录条数 | 执行方式与边界 |
| --- | ---: | --- |
| offscreen | 49 | 默认离屏；可使用真实本地模型和Windows OCR，但不操作当前桌面的键鼠。 |
| desktop | 4 | 真实窗口、屏幕、播放或物理输入。仅在独立runner或已获同意的空闲桌面运行。 |
| manual | 5 | 第三方应用、真实历史词本、人工听感、读屏和实际迁移。自动结果不替代这些验收。 |

模块编号：`window` 启动与窗口、`capture` 截图OCR、`boundary` 原文边界、`lookup` 词义卡片、`reading` 对照阅读、`learning` 词本统计、`language` 语言包与听读、`manual` 人工验收。优先级P0覆盖核心流程和数据/过期结果保护，P1覆盖扩展与兼容场景。

## 日常使用

从仓库根目录运行。Windows开发环境按README使用 `windows\setup.cmd` 准备；完整应用回归包含九种语言，需要先安装可选语言包。目录的检查、列举、导出只需要Python标准库，可在其他平台运行。

```powershell
# 校验用例编号、命中词、自动入口、语料编号和CSV一致性
.\.venv\Scripts\python.exe scripts\windows_regression.py check

# 浏览或筛选，不启动应用
.\.venv\Scripts\python.exe scripts\windows_regression.py list --group window
.\.venv\Scripts\python.exe scripts\windows_regression.py list --priority P0

# 执行窗口相关的现有离屏检查
.\.venv\Scripts\python.exe scripts\windows_regression.py run --group window

# 执行一个编号对应的自动检查
.\.venv\Scripts\python.exe scripts\windows_regression.py run --case WT-LOOK-001

# 完整离屏回归；桌面专用检查会跳过，人工项保持未验证
.\.venv\Scripts\python.exe windows\install_model.py --all-languages
.\.venv\Scripts\python.exe scripts\windows_regression.py run --full

# 修改JSON后重新生成Excel用例表
.\.venv\Scripts\python.exe scripts\windows_regression.py export
```

执行默认生成 `dist/regression/<UTC时间>.json` 和同名日志，记录命令、选择的目录编号、实际方法数、跳过项及仍待人工/桌面的编号。也可用 `--report` 指定结果文件。`automation_status`记录自动检查结果；存在跳过或人工待验收项时，整体`status`为`partial`。零检查或全部跳过会返回未验证；即使输出OK，进程退出异常仍判失败。

纯人工用例没有可执行入口，单独运行时会明确报错，按CSV步骤记录结果。`related_tests`只是辅助参考，不代表人工事项已被覆盖。

## 独立桌面验收

以下入口会显示窗口、移动鼠标、发送按键，部分项目会播放声音。开发代理在用户桌面运行前仍须按AGENTS.md说明影响并获得同意。现有Windows桌面CI优先使用真实便携包在100%/150%下执行。

```powershell
# 仅限独立runner或已获同意的空闲测试桌面
.\.venv\Scripts\python.exe scripts\windows_regression.py run --full --desktop

# 真实EXE启动、重复激活、任务栏样式和关闭/最小化
<便携目录>\runtime\python.exe windows\check_launcher.py <便携目录>
```

真实历史词本的升级必须用备份副本，不从空测试库推断用户数据升级已通过。人工记录建议使用「编号／版本与平台／倍率／实际结果／通过、失败或未验证／证据路径」六列。

## 固定输入与维护

JSON中的 `data.text` 可直接粘贴到对照页；`target` 是命中词，`occurrence` 从0开始，区分重复词。CSV导出的范围是Python Unicode字符的半开区间，不是UTF-16偏移；双端共享偏移以现有断句契约为准。

`fixtures`引用共享语料中的原始编号，实际输入、期望范围、结构与完整性都保留在原文件中。`automation`指向已有测试方法；新增场景若没有对应断言，应先补断言或声明人工验收，再更新目录，不能仅加入一个看似已自动覆盖的条目。

维护流程：编辑JSON → `export` → `check` → 执行受影响的组 → 必要时完整离屏/独立桌面。CI用标准库验证目录、测试入口和CSV，避免方法改名后目录失效。

## 已验证基线

应用源 `cc948d5c72b8716260e78d179d60b25a29438b5b`，合并提交 `23e8eae840504b36f7058deba2a0b0464558c584`，对应[任务栏与列间标题判断 PR #97](https://github.com/wax0629/WaxTranslate/pull/97)。

| 平台与命令 | 实际结果 |
| --- | --- |
| Windows本机 `windows/check.py -v` | 120项：116通过、4项要求独立桌面的检查跳过。 |
| 实际便携包 `windows/check.py --desktop -v`，100%/150% | 各120/120通过，无跳过；共享契约160/160。[独立桌面CI](https://github.com/wax0629/WaxTranslate/actions/runs/42843354986) |
| Windows原生多语OCR专项 | 真实截图2/2、识别路由16/16通过。[原生OCR CI](https://github.com/wax0629/WaxTranslate/actions/runs/42843354813) |

[该基线便携包](https://github.com/wax0629/WaxTranslate/actions/runs/42843354986/artifacts/13778150668)的GitHub artifact摘要为 `sha256:2ef9169ad761ee0a9bc55b026c8f8bbe28d01a470af9258764b4173f66f0f303`，它不是内部便携ZIP的摘要。基线是已验证的历史快照；以后修改应用后应记录新的运行结果。

5项纯人工验收保持未验证，不以这份自动化基线勾选。

## 测试集入口验证（2026-11-11）

- 工具单元测试13项通过，覆盖引用失效、重复编号、Unicode偏移、CSV漂移、桌面显式选择、纯人工项及退出异常判定。
- `run --group window`：实际执行9项检查，全通过，1.484秒。
- `run --full`最终复测：120项中116通过、4项桌面检查跳过，67.594秒，进程退出码0。自动检查为`passed`，包含人工/桌面待验收项的目录覆盖为`partial`，保留9个待执行编号。
- 初次全量运行在检查输出OK后出现退出异常`0xC0000409`，入口正确记录为失败；日志保留于`dist/regression/full-offscreen.log`。上述结果来自后续退出码0的完整复测，不覆盖首轮记录。

[机器可读验证摘要](validation.json)记录本轮命令、计数和报告路径。应用代码与上节已通过独立桌面验收的基线一致，本轮新增目录、工具与文档，不改应用行为。
