# 长句点词释义：本地修复

2026-11-11，接续 [Issue #102](https://github.com/wax0629/WaxTranslate/issues/102)，基于 `7b6897f` 及上一轮七项修复。本追加阶段只修订 Mac 的本机点词释义提取。以下为提交前的本机验收记录，源码摘要保留该验证时点；分支、PR 与后续 CI 状态以 Issue 正文为准。

## 改了什么

上一轮能译对整句，却会在 Apple 丢失格式对齐时留下「语境词义暂未确认」。这轮增加按确切原文位置恢复词义的路径：

1. 保留原来的整句/节选译文和点中词的位置。
2. 系统格式对齐失败时，在本机用最多三种内联标记定位该词；必要时利用它所在的相邻名词组合恢复义项，词头与收藏身份仍是原词。至少两种结果必须指向原始译文的同一范围。
3. 用周围文字、词边界和位置距离检查定位，重复词有竞争位置、结果互相冲突、标记丢失或请求失败时保留未确认，不从整句随便挑一个词典释义。
4. 对英语名词组合的中心词补齐对应的中文词边界，避免只显示词尾的一个字；点修饰词时保留其自身范围。
5. 恢复成功后正常显示、缓存和收藏。保存的仍是原词、完整原句和实际点击位置，不包含探针标记。

此实现不包含 bank 或固定译文的特殊分支，也没有引入云端服务或新模型依赖。Apple 对格式的保留属于尽力处理，其接口说明见 [attributedSourceText](https://developer.apple.com/documentation/translation/translationsession/request/attributedsourcetext)。

## 关键样文

| 场景 | 点中的词 | 预期 |
| --- | --- | --- |
| 长句河岸 | bank | 河岸/岸边，不能回退为银行或仅以未确认作通过 |
| 长句存款 | bank | 银行 |
| 同句先存款、后沿河走 | 前后两个 bank | 分别为银行和河岸，保留各自位置 |
| 词首、词尾、emoji | Bank / bank | 词义完整，UTF-16 偏移正确 |
| 否定、条件、词组 | bank / rule out | 词义与否定/条件原句对应 |
| 其他多义词 | bark / crane / charge | 树皮与叫声、起重机与鹤、充电；用于防止只对 bank 样例生效 |

```text
After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains.
After they had visited the bank to deposit their savings, they walked along the river bank before returning to the village for dinner.
```

## 验证

环境：macOS 26.6.2 Intel、Swift 6.3.3、SDK 26.5，已安装 Apple 英中语言资源。源码、夹具、截图摘要及分层结论见 [validation.json](validation.json)。

| 验证项 | 预期 | 实际 | 结论 |
| --- | --- | --- | --- |
| 修复前固定长句 | 必须返回河岸词义 | 新增回归实际失败：`long-river` 得到 unresolved | 已复现旧问题 |
| 真实 Apple 服务 | 固定长句、重复位置及其他词成功 | 16 个真实查询及 1 个无属性接口查询通过；河岸/银行、同句双义、条件与否定、句首句尾、emoji、其他多义词及词组均实际给出词义 | 通过 |
| 固定输出重放 | 同义表达、词序变化、原样词、丢失/冲突等可重复验证 | 10/10，其中 8 组恢复词义、2 组证据不足明确拒绝；另有 6 类异常输出、输入边界、重复歧义、失败及取消检查 | 通过 |
| 保存与缓存 | 正确释义可存，原句/位置不改，跨位置缓存隔离 | UTF-16 原位置、两次探针预算、缓存隔离、收藏重载和原句保持通过；真实挂载卡片会记录确认后的河岸词义 | 通过 |
| 完整 Mac 回归/布局/Release | 原流程不退化 | 160/160 共享断句、22 项真实 Vision、原生权限/百科/记录回归及 12/12 布局通过；Release 119.11 秒通过 | 通过 |
| 优化构建耗时样本 | 查询有界，记录恢复开销 | 同一系统会话连续三次返回河岸：2.15 / 1.63 / 1.65 秒；其中位置恢复 0.72–0.85 秒 | 已测量 |

真实服务与模拟 Provider 的结果分别记录；最低 macOS 实机和第三方应用物理手势不由本轮自动检查替代。缺少 EN/ZH 资源的 CI 只运行确定性检查，明确跳过真实服务样文。

耗时来自 `swiftc -O` 编译的翻译探针，包含准备、句译、重试及词义恢复；不含 OCR 与界面，未使用结果缓存。完整回归采用未优化构建，其首个长句在同时构建 Release 时为 6.44 秒，不能将这些记录当作跨设备的响应时间承诺。

## 本地查看

- 本机预览包位于验收工作树的 `dist/local-review-102-long/WaxTranslate Preview.app`，可双击启动；该本机产物未纳入源码仓库。使用独立的长句预览词本和偏好，默认仅应用内查词；前一版预览与已安装应用保留。
- [真实长句结果卡](mac-long-bank.png)：当前实际显示「河岸」，收藏可用；整句与节选译文保留。
- 本地原始日志在 `dist/local-review-102-long/evidence/`，最终 16 个真实查询以 `mac-final.log` 为准，`long-tests.log` 是前一轮 15 个样本的补充记录。

## 复跑

```sh
./scripts/check-long-context.sh
./scripts/check.sh
./scripts/check-card-layouts.sh
swift build -c release -j 2
./scripts/benchmark-macos.sh --reuse-session --long-context
```

确定性语料在 [context-word-alignment.json](../../../Tests/Fixtures/context-word-alignment.json)，测试入口在 [LongContextTests.swift](../../../Tests/waxtranlateTests/LongContextTests.swift)。
