# Windows 与 Mac 视觉同步

Issue #81；参考 Mac PR #80 f7f89d4（0.3.0 build11），Windows基线为main f6f651c。此次保留PySide6/Qt、本机翻译/OCR、数据库与Windows窗口行为，统一配色、字体层级、首页构图和取词卡。具体视觉规则见[DESIGN.md](../../../DESIGN.md)。

## 可重复验证

在隔离 Windows runner 使用便携包内解释器运行：

```powershell
runtime\python.exe windows\check.py --desktop -v
$env:QT_SCALE_FACTOR = '1.5'
runtime\python.exe windows\check.py --desktop -v
```

CI同一轮从PR基线和实际便携包分别加载模块，执行 `windows/capture_visuals.py`，在Qt Windows平台捕获100%/150%的宽窄首页、阅读、词本、设置与短词/句中/错误/长内容卡片，上传 `WaxTranslate-Windows-Visuals`。每张图的实际逻辑尺寸、物理像素与倍率在manifest.json中；固定释义和译文是排版夹具，不构成翻译准确性验收，完整真实模型/OCR检查由check.py单独执行。

截图使用临时数据库，进程和语言包查询不写用户词本或注册表；背景监听进程不启动，界面仍在实际Windows桌面上绘制。桌面手势与系统窗口操作由独立check.py覆盖。本机为macOS，不把本机静态检查或数据测试称为Windows界面验收。

## 结果与证据的位置

当前实现提交、Windows检查终态、截图复核结论和剩余项统一回写 [Issue #81](https://github.com/wax0629/WaxTranslate/issues/81) 与 [PR #82](https://github.com/wax0629/WaxTranslate/pull/82) 正文，避免把某次旧head的状态当成当前结果。

| 验证项 | 预期 | 直接证据 |
| --- | --- | --- |
| Python静态检查、统计数据 | 可解析，计数/迁移保持 | 本机compileall与7项数据回归；详细结果在PR正文 |
| Windows完整与桌面检查 | 100%/150%功能保持，操作无遮挡 | 当前head的Windows CI日志，包含每项用例和缩放倍率 |
| 原生视觉截图 | 两端视觉体系一致，宽窄和长内容可读 | 当前CI的WaxTranslate-Windows-Visuals产物及manifest |
| 便携包与启动 | 同一真实包正常启动、再次唤回、语言包可用 | 当前CI的启动/语言包阶段和WaxTranslate-Windows-x64产物 |

第一轮e72d8b0的[CI](https://github.com/wax0629/WaxTranslate/actions/runs/42575783108)在100%检查中97项有1项失败：首页根据初始640px宽度设了固定列宽，反过来抬高了主窗口的最小宽度；该轮150%功能检查未执行。修复将列宽设为布局上限，避免视口尺寸变成窗口最小值。初次通过透明窗口HWND捕获的卡片为黑色，截图器改取屏幕合成后的实际窗口矩形，不能把黑色图当视觉验收证据。最终结论以当前head检查和复核为准。

Windows仍有语音慢速菜单、真实音标/词性、双栏词本与平台窗口控件；这些是保留的功能和系统习惯。字体渲染由Windows/Qt承担，不以和Mac逐像素相同作为验收目标。
