---
title: GUI Guider 2.0 自定义字体文件名与 C 符号一致性
tags:
  - GUI-Guider
  - LVGL
  - font
  - code-generation
status: verified
date: 2026-07-29
---

# GUI Guider 2.0 自定义字体文件名与 C 符号一致性

## 原子结论

GUI Guider 2.0 的自定义字体文件基本名应使用可直接转换为 C 标识符的
字符，不要在扩展名前包含额外点号。

例如：

```text
不推荐：AlibabaPuHuiTi2.0.ttf
推荐：  AlibabaPuHuiTi2.ttf
```

## 为什么

同一个额外点号可能被页面生成器和字体转换器以不同方式归一化：

```text
页面引用：lv_font_AlibabaPuHuiTi2_0_23
字体定义：lv_font_AlibabaPuHuiTi2_23
```

结果是生成代码阶段正常，但 C 编译阶段出现 undeclared identifier。

## 可靠检查

生成后比较三个集合：

1. `generated/screens/*.c` 中的字体引用；
2. `generated/assets/fonts/gg_font.h` 中的声明；
3. `generated/assets/fonts/lv_font_*.c` 中的定义。

三个集合必须完全一致，随后执行一次全量模拟器构建。

## 已验证范围

- GUI Guider 2.0；
- Alibaba PuHuiTi 2.0 Regular；
- 17 个字号；
- 修复后完成 704 项全量构建；
- 用户确认实际字体显示成功。

## 不应推断

不能仅凭本案例断言所有 GUI 生成工具都存在相同缺陷。结论只适用于
具有“资源名 → C 符号”转换过程的工具链，使用前仍应验证。
