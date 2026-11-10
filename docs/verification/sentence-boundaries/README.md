# 换行与断句专项验收

Issue [#90](https://github.com/wax0629/WaxTranslate/issues/90)。基线 main `a79d70a`，Mac 先行；Windows 产品实现须在 Mac 当前提交验收通过后开始，不使用 Mac 的成功结果代替 Windows 检查。

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
| 实际卡片、Release、安装 | 片段标签和操作清楚，同身份升级 | 12类原生布局通过，[manifest](mac-layouts/manifest.json)及PNG已复核；当前提交构建/安装以Issue/PR最终记录为准 | 本机布局通过；构建安装见最终记录 |

真实识字图像由程序离屏绘制，不读取用户应用或真实词本，不启动桌面控制鼠标。示例：[完整跨行](vision/wrap-light-system.png)、[注释](vision/comments-dark-mono.png)、[两端裁切](vision/clipped-both-dark-mono.png)。布局截图采用固定的已声明释义，不算作模型准确性测试。

## 复现

在仓库根目录运行：

```sh
./scripts/check.sh
./scripts/check-card-layouts.sh /tmp/wax-sentence-layouts
swift build -c release -j 2
```

仅运行本专项：`./scripts/check-sentence-boundaries.sh`。可设置 `WAX_BOUNDARY_REPORT` 和 `WAX_BOUNDARY_IMAGES` 输出合成语料报告和真实 Vision 图像；没有真实用户内容。`WAX_BOUNDARY_BASELINE=1` 仅供在旧基线源代码上执行同语料对照，跳过旧版本不存在的字段/新运行时能力，不能用作新版本门禁。

此次共享 JSON 与两端测试必须保持同一版本。Windows 最终实际包、100%/150% 桌面检查、原生截图及提交对应关系由同一 Issue 与 Windows PR 独立记录。未取得平台证据时不勾选该平台验收。
