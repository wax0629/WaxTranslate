# WaxTranslate 公开试用前检查

2026-11-11 核查默认分支 `7b6897f`。建议当前继续小范围试用。开放给普通用户前，优先打通两端的公开下载和首次启动，解决会暴露阅读原文、打不开阅读页或给错语境的几项问题，再用同一份候选包从头验收。[跟踪 Issue #101](https://github.com/wax0629/WaxTranslate/issues/101)

本文保留 `7b6897f` 核查时的发现。随后七项缺陷与长句点词已修复并完成本机回归，详见 [修复验收](public-trial-fixes/README.md) 和 [长句点词](long-context/README.md)；当前分支及远程 CI 在 [Issue #102](https://github.com/wax0629/WaxTranslate/issues/102) 跟踪。下文旧源码行号仅用于定位当时问题。

## 从项目主页到第一次取词

| 平台 | 当前体验与证据 | 公开试用的验收动作 |
| --- | --- | --- |
| Windows 11 x64 | 仓库没有 Release。当前便携包约 597 MiB，需登录 GitHub 后下载并解压两层。匿名访问该产物链接本次得到 404，登录后可查到，保留至 2027-02-08。[当前构建](https://github.com/wax0629/WaxTranslate/actions/runs/42843354986) · [GitHub 下载规则](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts) | 提供带版本号的单层便携包。在没有 Python、没有 GitHub 登录的 Windows 11 上从主页下载、解压、首次启动，记录系统安全提示，断网查一个英语词，再从托盘打开阅读页。 |
| macOS | 仓库提供源码安装。当前本机 0.3.0 build 17 的 `codesign --verify --strict` 通过，Gatekeeper 的 `spctl --assess --type execute -vv` 返回 `rejected`，签名来源为 `waxtranlate local builds`。[安装与本地签名](../../scripts/sign-local.py) · [Apple 分发说明](https://developer.apple.com/developer-id/) | 提供可直接下载的 Developer ID 签名、公证包。用浏览器下载，在无开发工具、无旧授权的 Mac 上按默认安全设置打开，走完屏幕录制授权、语言包和首次翻译。 |

两端默认都可能只在托盘或菜单栏待命。建议首次主动启动时给出一个能直接试查的入口，先让用户在应用内读懂 `bank` 的两个例句，再引导到其他应用取词。Mac 的缺权限提示在同一进程只弹一次，用户关闭后再按快捷键会直接返回，建议给这个操作保留能找回的授权入口。反馈入口应能带出平台和构建号，供用户附上可公开的最短原句。[Mac 权限提示逻辑](../../Sources/waxtranlate/App.swift#L265)

## 产品问题与复验方法

| 建议顺序 | 已查到的行为 | 修订后怎样验收 |
| --- | --- | --- |
| 优先 · Mac 框选原文留存 | 用 Vision 识别固定样句 `The sample contains a green triangle.`，本机翻译并打开原生结果卡。未点收藏，重新读取隔离偏好域时收藏数为 0，整句仍作为「最近取词」的词头保存，首页会显示它。内容留在本机。[记录入口](../../Sources/waxtranlate/ResultCard.swift#L340) · [存储字段](../../Sources/waxtranlate/Notebook.swift#L117) | 建议默认仅为查词写最近记录，框选整段由用户主动保存。如保留选区历史，须让用户看清保存范围并能清除。用同一句分别查词、仅框选、主动保存，重启后核对首页和存储。 |
| 优先 · Windows 托盘阅读入口 | 在 Mac 用 Qt 6.12 离屏菜单调用产品的阅读入口函数，已隐藏的窗口切到阅读页后仍不可见，同条件下调用「打开」则可见。现有 Windows 阅读页测试先显示主窗才打开阅读页。[菜单与处理函数](../../windows/app.py#L432) · [现有测试](../../windows/check.py#L779) | 在 Windows 候选包分别从默认托盘启动、关闭到托盘、最小化三种状态点「对照翻译」，窗口应出现并能立即粘贴。 |
| 优先 · Windows 混排译向 | 源语言明确选英语，查 `The API returns a label named Beijing.` 的 API 会自动对照。只把地名换成「北京」，产品规则就判为中文语境、关闭自动句译。手动句译的代码此时选择中译英。[语境判定](../../windows/card_policy.py#L6) · [手动译向](../../windows/app.py#L752) | 两个英语句子都应自动译成中文。切回自动识别后用 `调用 API 查询北京。` 作对照，中文语境仍按需译成英文。分别实测编辑器和屏幕取词。 |
| 优先 · Mac 长句词义 | 本机短句的 river bank、存款处 bank 分别得到「岸边」「银行」。换成长句 `After a very long walk … they sat on the river bank …`，句译仍是「坐在河岸上」，主释义却回退为「银行」，卡片标为「单词参考」。现有测试允许这个结果。[固定样句与断言](../../Tests/waxtranlateTests/ReaderTests.swift#L532) | 将「点中的词义是否正确」和「全句是否译对」分别计分。对齐失败时，优先尝试命中分句；仍无可靠证据时，清楚提示当前词义未确认。 |
| 随后 · Windows 损坏语言包 | 在临时目录把法语翻译模型各文件写成 1 字节，把 OCR 文件填到正确长度。实际 `language_ready("fr")` 返回真，再调安装入口仍留下 1 字节模型；设置按此状态禁用下载。下载时已有校验，遗漏发生在已安装文件损坏后。[资源判定](../../windows/install_model.py#L68) · [设置按钮](../../windows/settings_page.py#L242) | 提供从设置修复的路径。截短翻译模型、破坏同尺寸 OCR 文件后，应能重新下载并完成一次实际查词。 |
| 随后 · Mac 百科设置 | 设置默认勾选「未收录的词自动补查百科参考」，取词卡只在用户点地球按钮后发出请求。代码中这个设置只被读写和展示，开关不改变查询行为。[设置项](../../Sources/waxtranlate/Panels.swift#L275) · [发起请求](../../Sources/waxtranlate/ResultCard.swift#L179) | 按当前手动查询的产品说明统一设置文案和入口。用未知词检查打开卡片时的请求次数、点按钮后发送的字段和断网重试。 |

## 候选包还需实机检查

| 场景 | 建议记录的结果 |
| --- | --- |
| 第三方应用与权限 | 在浏览器、双栏 PDF 和编辑器用同组样文做快捷键取词、框选、Esc 取消、连查两次。检查切屏、混合倍率双屏、浮窗焦点，以及 Mac 拒绝权限后再次触发、授权重启后的反馈。Mac 声明支持 15.2，但普通词的系统句中对齐接口要求 26.4+，应在最低支持系统验证回退并说明体验差别。[双端路线图](https://github.com/wax0629/WaxTranslate/issues/3) · [系统版本分支](../../Sources/waxtranlate/LookupTranslation.swift#L275) |
| 升级、迁移和退出 | 用有真实历史记录的词本**备份副本**覆盖升级，逐项比对词、原句、到期日和复习进度。Windows 另测便携目录迁移、真实登录后自启和反复退出。既往离屏检查有一次在输出 OK 后以 `0xC0000409` 退出，随后复测成功，原因仍未确定。[升级 Issue #1](https://github.com/wax0629/WaxTranslate/issues/1) · [Windows 执行记录](windows-regression/validation.json) |
| 离线首用与可访问性 | Windows 完整桌面回归前会先装齐可选包，需在只含默认包时断网试查，再测可选包下载中断与恢复。Mac 和 Windows 各做一次全键盘取词、收藏、复习，实际听中英混排、慢速和停止，并用 VoiceOver／讲述人检查标签与焦点。Mac 窄窗关闭、最小化、拖动和菜单栏唤回仍待组合验收。[Windows 工作流](../../.github/workflows/windows-desktop.yml#L39) · [Mac 窗口验收](https://github.com/wax0629/WaxTranslate/issues/79) |
| 准确性与等待时间 | 用同组多义词、术语、否定句和跨列样文，分别标注 OCR 命中、断句、主释义、句译。计时从按键到首条可读释义，分冷启动、重复查询和双屏场景。本机同一 Apple 会话三次固定查询为 334、156、111 ms，仅覆盖翻译阶段；已有一次受控屏幕取词全程为 2.49 秒。[历史分阶段计时](macos-sync/followup.md#分阶段耗时) |

## 核查依据

- **本次 Mac 本机**使用 macOS 26.6.2 Intel、Swift 6.3.3、SDK 26.5。运行 `./scripts/check.sh`、`./scripts/check-card-layouts.sh`、`swift build -c release -j 2`、`./scripts/benchmark-macos.sh --reuse-session`。160/160 项共享断句检查、22 项真实 Vision、12 类原生布局、已安装的 Apple 英中和日中服务及 Release 构建通过。当前 main 的 macOS arm64 CI 也通过，日志明确跳过了缺少英中包的真实句中对齐。[main CI](https://github.com/wax0629/WaxTranslate/actions/runs/42854128595)
- **Windows** 的 `windows/` 与 `Assets/` 在本次核查的 main 提交上和已验包提交 `cc948d5` 相同。该包在独立 Windows runner 上两档缩放各通过 120/120 项，多语 OCR 专项通过 2+16 项。本次在 Mac 复跑 Windows 断句契约（160/160）、SQLite 统计和旧库回归（7/7）、目录工具单测（13/13）及 58 条用例的目录校验。目录中 49 条离屏、4 条桌面、5 条纯人工。第三方应用、历史词本、听感、读屏、迁移自启这 5 条仍待人工执行。[桌面 CI](https://github.com/wax0629/WaxTranslate/actions/runs/42843354986) · [OCR CI](https://github.com/wax0629/WaxTranslate/actions/runs/42843354813) · [用例与命令](windows-regression/README.md)
- **README 截图**中的 Mac 取词卡和对照阅读页来自当前源码的原生视图，两处都使用 Apple 本机翻译的实际输出。Windows 首页和生词本来自上述桌面构建的 100% 截图，使用独立测试词本。四张图均使用示例内容。[README 界面预览](../../README.md#界面预览)
