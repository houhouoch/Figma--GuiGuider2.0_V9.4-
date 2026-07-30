---
title: GUI Guider 单行 Label 高度规范需要视觉闭环
tags:
  - GUI-Guider
  - Figma
  - typography
  - validation
status: pending-validation
date: 2026-07-29
---

# GUI Guider 单行 Label 高度规范需要视觉闭环

## 原子结论

Figma 文本边界、TTF 的完整字体度量和 GUI Guider Label 高度不是同一个
概念。转换后必须按字号统计高度分布，并通过实际 GUI/模拟器视觉检查后
才能固定规范。

## 当前项目证据

同为 23 px 的 Label 曾出现 28、30、33、34、36、40、42、54、77 px
等多个高度；26 px 也出现 30、35、37 px。

当前项目已静态统一为：

```text
普通单行 Label 高度 = 字号 + 5 px
23 px -> 28 px
26 px -> 31 px
```

静态检查结果：

- 普通单行 Label：666 个；
- 23 px → 28 px：165 个；
- 26 px → 31 px：66 个；
- 规则违反项：0。

## 待确认

- GUI Guider 逐页视觉检查；
- 生成 C 后的模拟器裁剪和基线检查；
- 该规则是否适用于其他字体；
- 该规则是否适用于其他 GUI Guider 版本。

在这些验证完成前，不应把“字号 + 5”写成跨项目通用规则或 Codex Skill。
