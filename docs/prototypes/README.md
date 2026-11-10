# 取词卡片交互原型

关联 [设计 Issue #83](https://github.com/wax0629/WaxTranslate/issues/83)。2026-11-09，待用户确认。

直接打开 `lookup-cards.html`，无依赖、无需构建、无需联网。此为固定内容交互原型，未接入Swift/Qt应用、OCR或翻译服务。

四类共11个样例：普通词短句/长句未消歧；VoiceOver确认/不确定与README；Redis/Docker/API与attention mask；UnknownSDK及识别不完整的token。可切换、展开原文/句译、查看候选/组成词、模拟收藏和固定、关闭后重新打开。朗读/复制/来源/重取仅说明动作，不调用系统。

验证：浏览器1280×720首屏与390×844窄屏，窄屏document宽390、scrollWidth390、卡片350，无横向溢出；实际点击API切换、按需英译、名称默认折叠、未知代码名组成词与禁用收藏通过。页面预览见 `lookup-cards-preview.png`。这些只证明原型呈现，不证明模型准确率、OCR或原生应用验收。

当前不改变安装版build12。用户确认信息层级、语境显示与展开规则后，再拆实现任务。原型不作为产品已实现的功能文档。
