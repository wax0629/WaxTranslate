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

| 验证项 | 预期 | 当前结果 | 结论 |
| --- | --- | --- | --- |
| Python静态检查、统计数据回归 | 可解析，真实统计/迁移保持 | compileall和7项数据测试通过 | 本机通过 |
| Windows完整与桌面检查 | 100%/150%功能保持，无遮挡 | 等待当前head的Windows CI | 待执行 |
| 原生视觉截图 | 两端视觉体系一致，宽窄和长内容可读 | 等待CI前后截图 | 待验收 |
| 便携打包与启动 | 同一真实便携包可启动、再次唤回、语言包可用 | 等待当前head的Windows CI | 待执行 |

Windows仍有语音慢速菜单、真实音标/词性、双栏词本与平台窗口控件；这些是保留的功能和系统习惯。字体渲染由Windows/Qt承担，不以和Mac逐像素相同作为验收目标。
