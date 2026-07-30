# GUI Guider 2.0 字体与 Label 高度问题复盘

日期：2026-07-29
工程：`D:\figma\V2.0\guiguider_2.0\guiguider_2.0`

## 1. 范围和证据

本复盘只覆盖本次会话中有证据支持的两类问题：

1. 自定义字体生成后的 C 符号不一致，导致模拟器编译失败。
2. Figma 转换后的单行 Label 高度不统一。

检查过的证据包括：

- 用户提供的 GUI Guider 模拟器编译错误；
- 正式工程 `guiguider_2.0.guiguider`；
- `resources/font/AlibabaPuHuiTi2.ttf`；
- `generated/screens/*.c` 中的字体引用；
- `generated/assets/fonts/gg_font.h` 中的字体声明；
- `generated/assets/fonts/lv_font_AlibabaPuHuiTi2_*.c` 中的字体定义；
- `tools/sync_completed_figma_to_guiguider.py` 的文本框处理逻辑；
- 修复前后的 JSON 结构与 Label 统计；
- GUI Guider 自带 MinGW/CMake 的 704 项全量构建结果；
- 用户对字体修复后实际显示效果的确认。

## 2. 问题一：自定义字体生成符号不一致

### 2.1 现象和影响

点击 GUI Guider 的“生成代码”后，模拟器在编译页面源文件时失败。

典型错误：

```text
error: 'lv_font_AlibabaPuHuiTi2_0_20' undeclared
did you mean 'lv_font_AlibabaPuHuiTi2_120'?
```

同类错误覆盖多个字号，例如：

```text
lv_font_AlibabaPuHuiTi2_0_13
lv_font_AlibabaPuHuiTi2_0_16
lv_font_AlibabaPuHuiTi2_0_18
lv_font_AlibabaPuHuiTi2_0_20
lv_font_AlibabaPuHuiTi2_0_23
```

影响范围：

- 27 个生成页面文件；
- 670 处错误字体引用；
- 17 个实际使用字号；
- 模拟器无法完成链接，后续 MDK 同步也不应继续。

### 2.2 复现条件

同时满足以下条件即可复现：

1. GUI Guider 工程中的 `text_family` 仍为
   `AlibabaPuHuiTi2.0.ttf`；
2. 实际资源已经改名为 `AlibabaPuHuiTi2.ttf`；
3. 页面生成器把文件名中的额外 `.` 转成 `_0`；
4. 字体转换器生成的符号不包含 `_0`。

最终形成：

```text
页面引用：lv_font_AlibabaPuHuiTi2_0_23
头文件声明：lv_font_AlibabaPuHuiTi2_23
字体定义：lv_font_AlibabaPuHuiTi2_23
```

### 2.3 直接原因和根本原因

直接原因：

- 页面代码引用了未声明、未定义的 `_2_0_` 字体符号。

根本原因：

- 自定义字体文件基本名包含额外的点号 `2.0`；
- GUI Guider 2.0 的页面生成和字体转换对该点号采用了不同的
  C 标识符归一化方式；
- 仅重命名字体文件，没有同步工程内全部 `text_family` 字段。

### 2.4 失败或不完整的方法

#### 只重命名 TTF 文件

将：

```text
AlibabaPuHuiTi2.0.ttf
```

改为：

```text
AlibabaPuHuiTi2.ttf
```

并不能单独解决问题。正式工程中仍有 670 个旧字段，生成页面仍使用
`_2_0_` 符号。

失败原因：资源文件名、工程字段和生成代码没有作为一个契约整体更新。

#### 只修改一个页面或一个字号

错误分布在 27 个页面、17 个字号中。只修
`gg_HOME_MENU.c`、`gg_screen_group.c` 或某个字体声明会让后续页面继续失败。

失败原因：问题是全局命名契约不一致，不是单文件缺少声明。

### 2.5 最终解决方案

1. 使用不含额外点号的字体资源：

   ```text
   resources/font/AlibabaPuHuiTi2.ttf
   ```

2. 将正式 `.guiguider` 中 671 个字体字段统一为：

   ```json
   "text_family": "AlibabaPuHuiTi2.ttf"
   ```

3. 将当前生成页面中的 670 个 `_2_0_` 引用统一为 `_2_`。
4. 保持 `gg_font.h` 声明和字体 C 文件定义不变，因为它们原本已经一致。

原始字体来源：

```text
D:\资料\AlibabaPuHuiTi-2\AlibabaPuHuiTi-2-55-Regular\AlibabaPuHuiTi2.ttf
```

工程字体与原始字体 SHA-256 均为：

```text
A22AD467D9D6B4C9A0B2E033927ED41592743C987546A7397215CE96B850743B
```

### 2.6 验证

静态验证：

- 工程旧字体字段：0；
- `_2_0_` 旧生成符号：0；
- 页面引用字号：17；
- 头文件声明字号：17；
- 字体 C 定义字号：17；
- 三个符号集合完全一致。

构建验证：

```text
[704/704] Linking CXX executable bin\simulator.exe
Exit code: 0
```

实际结果：

- 用户重新打开 GUI Guider 后确认字体修复成功。

结论：字体问题已验证闭环。

## 3. 问题二：单行 Label 高度不统一

### 3.1 现象和影响

相同字号的单行 Label 在正式工程中存在多种高度。

修复前的典型分布：

```text
23 px -> 28 / 30 / 33 / 34 / 36 / 40 / 42 / 54 / 77 px
26 px -> 30 / 35 / 37 px
```

其中主要错误分布为：

```text
23 px -> 33 px：144 个
26 px -> 37 px：45 个
```

表现为同一页面或不同页面之间文本框高度、基线和上下留白不一致。

### 3.2 直接原因和根本原因

直接原因：

- 转换结果保留或扩张了不同来源的文本框高度，没有执行统一的单行
  Label 几何规范。

根本原因：

- Figma 文本边界、TTF 完整字体度量和 GUI Guider 的紧凑 Label
  高度是三个不同概念；
- 当前转换逻辑曾使用 TTF 的 `ascent + descent` 参与高度校正；
- 项目需要的视觉标准是紧凑单行框，而不是完整字体行框；
- 该标准此前没有成为可执行的项目验收项。

### 3.3 尝试过但未采用的方法

#### 重新修改 Figma 转 GUI Guider 脚本

曾尝试把统一规则加入转换器，但用户明确要求本次只修改现有
GUI Guider 工程，不重新执行 Figma 转换。

未采用原因：

- 超出本次“只修正式 GUI Guider 页面”的范围；
- 重新转换可能覆盖已经完成的 GUI Guider 手工调整；
- 本次最快、风险最小的路径是直接修改正式 `.guiguider`。

该脚本改动已撤回。

#### 受父容器高度限制

最初把 Label 高度限制在父容器高度内，导致少数 Label 仍不满足统一
规则，例如 26 px 的两个 RUN 标签仍为 30 px。

未采用原因：与用户明确指定的 26 px → 31 px 不一致。

### 3.4 当前解决方案

只直接修改正式工程：

```text
D:\figma\V2.0\guiguider_2.0\guiguider_2.0\guiguider_2.0.guiguider
```

规则：

```text
普通单行 Label，高度 = 字号 + 5 px
```

限制：

- 仅处理带 Figma ID 的 Label；
- 仅处理字号小于 80 px 的单行文本；
- 多行文本不改；
- 80 px、120 px 大数字不改；
- 保持控件中心位置，必要时同步调整 `y`；
- 不改名称、ID、层级、样式和业务字段。

结果：

```text
普通单行 Label：666 个
23 px -> 28 px：165 个
26 px -> 31 px：66 个
违反规则：0
```

### 3.5 验证状态

已验证：

- `.guiguider` 是合法 JSON；
- Figma/GUI Guider 节点 ID 集合未变化；
- 直接修改只涉及 Label 的 `height` 和 `y`；
- 666 个普通单行 Label 全部满足静态高度规则；
- 23 px、26 px 两个用户明确指定的规则均满足。

待确认：

- GUI Guider 中逐页视觉检查；
- 重新点击“生成代码”后，生成 C 是否完整反映新高度；
- 模拟器对所有页面的裁剪、基线和焦点视觉检查；
- 高度“字号 + 5”是否适用于其他字体、其他 GUI Guider 版本。

因此，本规则目前只能视为当前项目的静态工程规范，不能写成跨项目
通用结论。

## 4. 防回归检查清单

### 4.1 自定义字体

- [ ] 字体文件基本名只使用字母、数字和下划线，不包含额外点号。
- [ ] `.guiguider` 的 `text_family` 与 `resources/font` 文件名完全一致。
- [ ] 统计生成页面中的字体引用符号。
- [ ] 统计 `gg_font.h` 中的声明符号。
- [ ] 统计字体 C 文件中的定义符号。
- [ ] 引用、声明、定义三个集合必须完全相同。
- [ ] 至少执行一次全量模拟器构建。
- [ ] 在 GUI Guider 或模拟器中确认没有字体回退、缺字、错位或裁剪。

### 4.2 Label 高度

- [ ] 转换后按字号统计单行 Label 高度分布。
- [ ] 多行 Label 与单行 Label 分开检查。
- [ ] 大字号动态数值与普通 Label 分开检查。
- [ ] 直接修改 `.guiguider` 前关闭 GUI Guider 并建立备份。
- [ ] 修改后验证 JSON。
- [ ] 比较节点 ID、名称、层级和业务字段是否保持不变。
- [ ] GUI Guider 中逐页检查基线、裁剪和上下留白。
- [ ] 重新生成代码后再运行模拟器。

## 5. 经验归属判断

| 目的地 | 结论 | 原因 |
|---|---|---|
| 项目复盘文档 | 是 | 两个问题均有当前工程的完整证据链 |
| 当前项目 `AGENTS.md` | 部分进入 | 字体命名和三集合校验已验证；Label 精确高度尚未视觉闭环 |
| 跨项目 Codex Skill | 暂不进入 | 只验证了 GUI Guider 2.0 和一个字体，证据不足以泛化 |
| Obsidian | 是 | 提取字体命名契约和“视觉规范必须闭环”两个原子知识 |
| 待验证假设 | 是 | “字号 + 5”跨字体、跨版本适用性尚未验证 |
