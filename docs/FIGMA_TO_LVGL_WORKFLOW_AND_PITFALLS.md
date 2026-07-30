# Figma 到 LVGL 的三条路线：实测复盘与避坑指南

> 本文面向希望使用 Figma 设计嵌入式界面，并最终生成 LVGL C 代码的开发者。
> 记录时间：2026-07-23。
> 实测工具：LVGL Pro Editor、LVGL 9.5.0、GUI Guider 2.0.0、LVGL 9.4.0、Keil MDK。
> 本文是工程复盘，不是对工具厂商或后续版本的永久评价。

## 1. 为什么写这篇文档

我们的目标一直很明确：

1. 使用 AI 和 Figma 快速完成工业仪表 UI 设计。
2. 将设计转换成可以运行在 STM32 上的 LVGL C 代码。
3. 保留可视化编辑能力，避免每次修改页面都重新手写坐标和样式。
4. 让按钮、LED、动态数值等对象保留正确的 LVGL 控件语义。
5. 生成结果可以进入 Git、Simulator 和 MDK，发生问题时能够回滚。

实际尝试了三条路线：

```text
路线 A：Figma -> LVGL Pro/Flow -> XML -> LVGL 9.5 C

路线 B：Figma -> JSON/SVG/TTF -> 自定义生成器 -> 原生 LVGL 9.5 C

路线 C：Figma -> 结构化 JSON -> 校正规则 -> GUI Guider 2.0
       -> LVGL 9.4 C -> Simulator -> MDK
```

最终选择路线 C，但不是把 Figma 插件输出直接作为最终工程，而是在 Figma 和 GUI Guider 之间保留一层结构校验与规范化。

## 2. 版本和项目边界

本次复盘包含两个不同的实际界面工程：

| 阶段 | 界面 | 分辨率 | LVGL |
| --- | --- | --- | --- |
| LVGL Pro 和原生生成器试验 | ZDYZ 电源界面 | 800 x 480 | 9.5.0 |
| GUI Guider 2.0 试验 | UDP3900 电源界面 | 960 x 240 | 9.4.0 |

这两个项目不是同一分辨率，因此不能只根据截图做严格的像素优劣比较。本文比较的是转换能力、结构可靠性、维护成本和实际遇到的问题。

官方资料与本次版本选择一致：

- [LVGL 9.5 Editor 文档](https://docs.lvgl.io/9.5/xml/editor/overview.html)说明 Editor 可以从 XML 导出 C，并将 Figma 插件定位为加速设计重实现的工具。
- [NXP GUI Guider 2.0.0 发布说明](https://community.nxp.com/t5/GUI-Guider-Knowledge-Base/GUI-Guider-2-0-0-just-released/ta-p/2389764)明确列出 Figma 项目导入，并说明该版本升级到 LVGL 9.4.0。

## 3. 第一阶段：LVGL Pro + Figma 插件 + LVGL 9.5

### 3.1 最初的预期

最初希望得到以下流程：

```text
Figma 整屏设计
  -> LVGL Flow for Figma 插件
  -> LVGL Pro Editor
  -> 直接导出 .c/.h
  -> Keil MDK
```

这个方案看起来最接近“一键转换”：LVGL Pro 有 XML、实时预览、CLI 和 C 代码生成能力，LVGL 9.5 又是当时项目使用的新版本。

### 3.2 对 Figma 集成能力的错误预期

我们一开始把插件理解成“整屏、自动、像素级、语义完整导入器”。这与工具的实际定位不一致。

LVGL 9.5 的官方说明使用“加速重实现 Figma 设计”，当前的 [Figma Flow 文档](https://lvgl.io/docs/pro/figma)则说明插件会把设计转换成可编辑的 LVGL XML，同时仍由开发者控制最终结构。两者都没有承诺任意 Figma 设计可以在不复核结构和语义的情况下，自动得到像素级、业务语义完整的固件 UI。

这意味着插件更适合：

- 提取颜色、尺寸、圆角、边框等样式。
- 将 Figma 节点与 XML 样式建立关联。
- 加速已有 LVGL 组件的样式同步。

它并不天然知道：

- 某个圆点是 LED，而不是普通 Rectangle。
- 某个 Frame 是 Button，而不是 Container。
- 某个数值需要运行时更新。
- 某个图标应该作为 Image 资源，而不是拆成多条 Line。
- 某组图层应怎样拆成可维护的 LVGL Component。

### 3.3 本地服务和同步链较长

本次使用的插件需要 Figma、LVGL Pro、本地项目和服务端口共同工作。实际遇到过：

- LVGL Service 显示 `Not running`。
- `Start Service` 点击无反应。
- 输出目录选择错误。
- Figma 插件显示 Connected，但 Editor 内容没有更新。
- Figma 删除图层后，旧 XML 或旧资源仍留在项目中。
- 点击 Export 后没有清晰的成功提示，不容易判断写入了哪些文件。
- Figma、Chrome、Codex 和 LVGL Pro 使用不同账号或会话时，连接状态难以判断。

这类问题的本质不是 LVGL 绘制错误，而是同步链包含多个状态：

```text
Figma 当前文件和选区
  + Figma 插件授权
  + 本地服务是否运行
  + 服务端口
  + 输出目录
  + LVGL Pro 当前打开的项目
  + 旧文件是否被清理
```

任何一项不一致，都可能产生“插件说已连接，但工程没有真正更新”的结果。

### 3.4 XML 不是最终 C，而是另一层工程模型

LVGL Pro 首先生成或维护 XML，再由 Editor/CLI 生成 C。XML 的价值很高：可读、可版本管理、可复用、可预览。但它也增加了一层必须正确的中间模型。

本次出现过：

```text
The currently opened XML file is invalid and cannot be previewed.
```

以及 `globals.xml` Parse error。需要特别澄清：当时讨论的“命名渐变”并不是 Figma 图层名称包含“渐变”两个字，而是插件生成了带名称的全局 Gradient 定义，并在页面 XML 中通过 `style_bg_grad` 引用。导出结构与当时 Editor 接受的 XML Schema 不一致，才导致预览失败。

历史工程中最后不得不增加 XML 修复脚本，处理：

- 将全局命名 Gradient 转成对象上的 LVGL 两色渐变属性。
- 将不支持的多段 Gradient 降级为首尾颜色或近似两段渐变。
- 将文件型 TTF 声明转换成可嵌入的字体定义。
- 删除 Editor 无法识别的全局 Gradient 节点。
- 对每个 XML 文件重新解析和写回，确认语法有效。

一旦转换流程需要先修复插件 XML，再修复生成 C，所谓“一键导出”的维护优势就会快速降低。

### 3.5 生成代码与固件 LVGL 配置不一致

实际链接时出现过：

```text
Undefined symbol lv_obj_set_name_static
Undefined symbol lv_translation_add_static
Undefined symbol lv_translation_set_language
```

历史导出代码中确实生成了 `lv_obj_set_name_static()`。LVGL Pro Simulator 默认配置还启用了 Object Name 和 Translation，而 STM32 Pack 工程没有完全包含相同的功能模块或配置组合。

这类错误不能简单通过“再添加一个 C 文件”解决，必须同时检查：

- 生成器所针对的 LVGL 小版本。
- `lv_conf.h` / `lv_conf_cmsis.h` 中的功能开关。
- Pack 实际编译了哪些 LVGL 模块。
- Simulator 默认配置与固件配置是否一致。
- 生成代码是否无条件调用了可选功能 API。

本次为适配 ARMCC5 和固件配置，还增加过生成后处理脚本，例如给仅在 `LV_USE_XML` 下有效的字体检查代码增加条件编译，并修复生成文件末尾换行。

### 3.6 视觉还原度不稳定

Figma 参考图与 LVGL Pro 导出结果存在明显差异：

- 面板边框和渐变被简化。
- 光晕和阴影不一致。
- 字体、字重、字号和基线有差异。
- 图标被错误替换或拆解。
- 复杂矢量产生大量小图片或基础对象。
- 页面比例接近，但局部间距和对象边界不准确。
- Figma 的 Auto Layout、Mask、Blend Mode 和复杂效果无法直接对应 LVGL。

这并不表示 LVGL 不能实现这些效果，而是 Figma 的视觉模型无法自动一一映射到有限的 LVGL Widget、Style 和资源模型。

### 3.7 删除和重新导出不等于镜像同步

Figma 中删除对象后，目标目录里的旧 XML、图片或 Manifest 不一定自动删除。如果直接覆盖导出而不清理旧文件，会出现：

- Editor 仍能读取已经从 Figma 删除的页面或组件。
- Manifest 与实际文件不一致。
- 新旧资源同时存在。
- 误以为 Figma 删除没有生效。

正确做法是把导出视为构建过程：保留原始快照，清理受生成器管理的目录，重新生成，再通过 Git Diff 确认删除项。

### 3.8 许可边界必须单独核对

LVGL C 库本身使用 MIT License，但 LVGL Pro Editor、XML Specification 和相关工具有各自的许可条款。尤其准备把 XML 处理器、转换器或生成器公开到 GitHub 时，应阅读本次使用版本对应的 [LVGL 9.5 XML License](https://docs.lvgl.io/9.5/xml/xml/license.html)，发布前还应再次核对官方最新条款。

本文不是法律意见。稳妥做法是：

- 可以公开自己的应用代码、设计经验和问题记录。
- 字体、图片和图标分别检查许可证。
- 准备公开会读取或生成 LVGL XML 的工具前，重新核对官方最新条款。
- 不要假设“LVGL 是 MIT”就代表 LVGL Pro 的所有工具和 XML 规范也完全等同于 MIT。

### 3.9 第一阶段结论

LVGL Pro 的 XML、预览和生成能力本身有价值，但本项目需要的是“复杂 Figma 整屏自动转换成接近最终效果的 C”。在这个目标下，插件输出仍需要大量结构修复、资源整理和版本适配，因此我们停止将它作为生产主路径。

历史 Git 回滚点：

```text
28fbdf4  feat(ui): add Figma Flow LVGL Pro export
2d91861  chore(ui): checkpoint before Figma resync
47fbd58  chore(ui): archive final LVGL Pro export attempt
```

## 4. 第二阶段：Figma 数据直接生成原生 LVGL 9.5 C

### 4.1 为什么改成原生生成器

放弃 LVGL Pro 自动整屏导入后，我们使用：

```text
Figma frame
  -> Figma MCP/AI 提取布局和 SVG
  -> 版本化 JSON Manifest
  -> 本地生成器
  -> 原生 LVGL 9.5 C、字体和图片
  -> Keil MDK
```

该方案比一次性手写 C 更可靠，因为坐标、样式、字体和资源由脚本重复生成；也比修复 LVGL Pro XML 更直接，因为最终输出就是目标 LVGL 版本的 C。

### 4.2 该方案的优点

- 可以严格控制坐标、尺寸、颜色和资源。
- 可以针对 LVGL 9.5 API 生成代码。
- 生成文件、JSON 和图片全部可以进入 Git。
- 可以保留手写业务层，避免重新生成时覆盖事件和产品逻辑。
- 对不支持的效果可以明确选择“近似 LVGL Style”或“预渲染图片”。
- 实际工程已经完成 Keil 链接和 HEX 生成。

历史提交：

```text
d0d8978 feat(ui): replace LVGL Pro with native Figma generator
```

### 4.3 直接生成 C 的主要缺点

#### 缺少通用可视化中间层

设计修改后，需要重新生成预览、编译或下载到板卡。虽然可以做 PC 预览，但不如成熟 GUI 工具方便地选中对象并修改属性、事件和控件类型。

#### 生成器需要持续维护

每增加一种效果或控件，都需要实现对应规则：

- `lv_obj_t`、`lv_label`、`lv_image`、`lv_line`。
- 字体转换和字符子集。
- RGB565/RGB565A8 图片转换。
- 渐变、边框、阴影、状态样式。
- 事件和业务回调接口。

#### AI 或 Figma 数据不知道业务语义

从视觉上看，一个绿色圆点只是圆形；它是否应该使用 `lv_led`，取决于业务。一个设定值框是否应该是 Button、TextArea、Spinbox 或普通 Container，也无法仅靠截图确定。

#### 设计和生成器高度耦合

Figma 图层名称、JSON Schema 或层级一旦变化，生成器也要更新。缺少严格命名规范时，脚本会快速变成大量特例。

#### 生成代码所有权必须划分

需要明确：

- `*_gen.c/.h` 只能由生成器修改。
- 业务事件和状态更新放在稳定的手写文件中。
- 资源源文件与生成后的 C 分开保存。

如果没有这个边界，重新生成会覆盖手工逻辑。

### 4.4 第二阶段结论

原生生成器的视觉还原和版本控制优于第一次 LVGL Pro 自动导出，但对多页面产品来说，自建完整 UI 编辑器和生成器成本过高。因此我们希望增加一个能直观看到 LVGL 结果、能修改 Widget 语义、又能稳定生成 C 的中间层。

## 5. 第三阶段：GUI Guider 2.0 + LVGL 9.4

### 5.1 为什么选择 GUI Guider 2.0

NXP 在 GUI Guider 2.0.0 中加入了 Figma-to-GUI Guider Project Import，并升级到 LVGL 9.4.0。它正好提供我们缺少的中间层：

```text
Figma 负责设计
GUI Guider 负责 LVGL Widget、事件、预览和代码生成
MDK 负责硬件集成
```

相对直接生成 C，它的优势是：

- 可以直接看到 GUI Guider 中的 LVGL 结果。
- 可以把普通形状修正为 Button、LED、Image 等真实控件。
- 可以继续调整内边距、状态样式和事件。
- C 代码生成由 GUI Guider 管理，减少自建生成器的范围。

### 5.2 GUI Guider 的 Figma 插件仍不是无损导入器

第一次直接下载插件生成的 GUI Guider 包后，效果与 Figma 仍有明显差异。最初怀疑只有字体问题，后来确认至少包含以下三类原因：

1. Figma 源图层尺寸不合法。
2. 插件 Design Tree 控件映射错误。
3. 字体文件和 LVGL 字体度量不一致。

### 5.3 Design Tree 类型映射会改变 Project JSON

插件界面中的类型下拉框不是备注，而是 JSON 生成规则。自动映射曾出现：

- 1 px/2 px 的装饰 Rectangle -> Container。
- `button_menu` -> Container。
- `button_mode_select` -> Container。
- `input_vset` / `input_iset_pos` / `input_iset_neg` -> Container。
- `indicator_system_ready` -> Container。

错误结果会直接改变最终 C API。例如：

```text
错误：lv_obj_create(...)
正确按钮：lv_button_create(...)
正确 LED：lv_led_create(...)
```

本项目校正后的映射：

| Figma 用途 | GUI Guider / LVGL 类型 |
| --- | --- |
| 根画板 | Screen |
| 普通背景面板 | Container |
| 文本 | Label |
| 菜单和模式选择 | Button |
| 三个设定值输入区域 | Button |
| 系统就绪状态圆点 | LED |
| 原始图标 | Image |
| 纯装饰细直线 | Line 或无背景对象 |

### 5.4 Figma 文本框可以视觉越界，LVGL 会裁剪

`label_menu` 是最明确的案例：

- Figma 节点：`74:12`。
- 字号：24 px。
- 实际文本框约为 65 x 14 px。
- Figma 画布上仍能看到完整文字。
- 插件 JSON 又将尺寸导出成 `0/content`。
- GUI Guider/LVGL 按真实对象边界裁剪，最终只显示部分 `MENU`。

根因在 Figma 源图层给出的高度太小，不是 GUI Guider 随机破坏字体。

正确处理：

1. 在 Figma 中将文字框高度设置为足够值，例如约 28 px。
2. 或使用可验证的 Auto Height，并确认导出后的实际高度不是 0。
3. 明确设置 Line Height。
4. 固定分辨率仪表中的关键文字使用明确 px 宽高。

### 5.5 字体问题需要拆成三个问题判断

不要把所有文字异常都叫“字体问题”。应分别检查：

1. **Figma 文本框是否足够大。**
2. **GUI Guider 是否使用同一份 TTF。**
3. **LVGL 字体的 ascent/descent 和基线是否需要目标端补偿。**

大字号 `label_vout`、`label_iout` 使用 120 px 字体时，源框合法后仍存在 LVGL 基线差异，因此当前目标端使用约 `pad_top=-20` 的补偿。这个补偿不能拿来掩盖 `label_menu` 只有 14 px 高的问题。

### 5.6 插件不会自动嵌入完全相同的字体

Figma 引用字体家族和样式；GUI Guider/LVGL 最终需要真实 TTF 和生成后的位图字体。字体名字相似不代表二进制字体相同。

本项目进行了显式字体映射，并把 TTF 放入：

```text
resources/font/
```

验收必须检查：

- JSON 中每个字体家族都有本地文件。
- GUI Guider 生成了实际使用字号的 LVGL 字体。
- 最长动态字符串不会溢出。
- 数字、单位和标题分别检查基线。

### 5.7 图标和复杂矢量需要作为资源处理

状态栏图标曾出现锁、保护和菜单图标错误。复杂图标不适合让插件拆成基础对象，也不应使用“看起来相似”的图标替代。

当前规则：

- 使用 Figma 原始图标。
- 复杂 SVG/Vector 导出为 Image 资源。
- 保留透明通道。
- 在 GUI Guider 中检查 RGB565/RGB565A8 转换结果。
- 动态状态用外层 Widget 控制，不通过替换任意近似图标表达。

### 5.8 渐变、光晕和阴影仍需要降级设计

GUI Guider/LVGL 可以实现两色线性渐变、边框、圆角、普通阴影和透明度，但无法自动复刻所有 Figma 效果。

推荐原则：

- 与状态相关、需要动态变化的部分使用 LVGL 原生 Style。
- 复杂但静态的装饰可以预渲染为图片。
- 不使用 Background Blur、复杂 Blend Mode、多层 Mask 作为关键视觉信息。
- 光晕要克制，并在 RGB565 实际屏幕上检查色带和性能。

### 5.9 插件导出项目不能直接覆盖本地工程设置

插件导出的 Project JSON 可能包含自己的 Board、路径、版本和默认配置。直接覆盖本地工程会破坏：

- LVGL 9.4.0 配置。
- 960 x 240 分辨率。
- RGB565 色深。
- Simulator 和本地资源路径。

最终方案是：

```text
本地 GUI Guider 2.0 空白工程
  + Figma 导出的 UI 节点树
  + 人工确认的语义映射
  + 字体和图片资源
  + 自动校验
  = 可重复生成的 guiguider_2.0.guiguider
```

对应脚本：

```text
tools/build_figma_screen.py
```

### 5.10 GUI Guider JavaScript Simulator 不是最终验收

JavaScript Simulator 适合快速检查，但最终固件使用生成的 C 和 LVGL 字体。验收顺序应为：

1. GUI Guider UI Editor。
2. JavaScript Simulator。
3. 重新生成 C。
4. C/C++ Simulator。
5. STM32 实板。

### 5.11 工程移动后 CMake 缓存会保留旧路径

本次 GUI Guider 工程从其他目录移动到 `D:\figma` 后，CMakeCache 仍指向旧路径，导致 C/C++ Simulator 构建失败。

解决步骤：

1. 清除编译目录。
2. 重新生成 C。
3. 重新构建 Simulator。

最终成功记录：

```text
[546/546] Linking CXX executable bin\simulator.exe
Build completed successfully
```

编译成功只证明代码可构建，不能替代视觉、控件类型和事件检查。

## 6. 两种 Figma 插件路线的共同缺点

| 问题 | LVGL Pro / Flow | GUI Guider 2.0 Figma Import |
| --- | --- | --- |
| 任意整屏无损转换 | 不保证 | 不保证 |
| 自动理解 Button/LED/动态值 | 不可靠 | 不可靠，需要 Design Tree 校正 |
| Figma Auto Layout 等价迁移 | 不可靠 | 不可靠 |
| 字体自动嵌入 | 仍需字体资源和配置 | 仍需字体资源和字号生成 |
| 复杂 Gradient/Blur/Mask | XML/Style 可能降级或无效 | 需要 Style 降级或图片化 |
| 图标处理 | 可能拆成大量资源/对象 | 可能错误映射，需 Image 化 |
| 删除后的同步 | 可能留下旧 XML/资源 | 重新导出前也应检查旧对象 |
| 业务语义 | 需要开发者补充 | 需要开发者补充 |
| 版本耦合 | Editor/XML/生成器/LVGL 配置需一致 | GUI Guider 版本与其 LVGL 模板需一致 |
| 最终验证 | Editor + 固件 | JS Simulator + C Simulator + 固件 |

共同根因是：Figma 图层表达的是设计结构，而 LVGL 工程需要运行时控件结构。两者不是同一种模型。

## 7. 三条路线的实际取舍

| 路线 | 优点 | 主要缺点 | 本项目结论 |
| --- | --- | --- | --- |
| LVGL Pro + XML + 9.5 | XML 可读、可预览、可生成 C | 服务和 XML 链复杂；整屏导入仍需重构；版本配置敏感 | 不再作为主路径 |
| 自定义原生 C + 9.5 | 还原可控、C 直接、Git 友好 | 生成器维护成本高；缺少成熟可视化中间层 | 证明可行，作为回退方案 |
| GUI Guider 2.0 + 9.4 | 可视化修改、Widget 语义、C 生成成熟 | 插件映射和文字几何仍需校正 | 当前主路径 |

没有真正“完全不需要开发者”的路线。我们的选择标准不是点击次数最少，而是问题能否定位、结果能否重复生成、代码能否维护。

## 8. 最终推荐流程

```text
1. Figma 设计
   - 固定分辨率
   - 合法命名
   - 合法文字框
   - 明确控件语义

2. 导出原始结构化数据和资源
   - 原始 JSON 只读保存
   - 图标/图片保留原始文件
   - 字体保存许可证和 TTF

3. 规范化和校验
   - 修正 Widget 类型
   - 固定关键 Label 尺寸
   - 标记动态文本
   - 校验名称、ID、字体和图片路径

4. 合并到 GUI Guider 2.0 本地工程
   - 保留 LVGL 9.4、960 x 240、RGB565 配置
   - 不直接覆盖整个 Project JSON

5. GUI Guider 中人工验收
   - 控件树
   - 字体
   - 图标
   - 渐变
   - 事件

6. 生成和验证
   - Generate C
   - C/C++ Simulator
   - Git Diff
   - MDK 编译
   - 实板触摸和长期运行
```

## 9. Figma 设计前置规范

### 命名

- 只使用 ASCII 字母、数字和下划线。
- 使用唯一的 `snake_case`。
- 通过名称表达语义：`button_`、`label_`、`indicator_`、`img_`、`decor_`。
- 不使用中文、空格、斜线、括号和特殊乘号作为代码对象名。

### 文字

- 字号、Line Height、Width、Height 都要明确。
- 不允许依赖字形越过文本框边界显示。
- 动态值按最长字符串预留宽度。
- 使用最终 TTF 检查大字号数字。

### 图层

- Button 的点击区域与内部 Label/Image 分层。
- LED 状态图层单独命名。
- 1 px/2 px 装饰线单独命名。
- 复杂图标保持为可导出的 Vector/Image。
- 避免过深、无语义的 Group/Frame 嵌套。

### 效果

- 只把 LVGL 可实现的效果作为关键状态表达。
- 复杂静态装饰可以图片化。
- 不让 Blur、Mask、Blend Mode 承担功能信息。

## 10. 进入 MDK 前的验收门槛

### 结构

- [ ] Screen 分辨率正确。
- [ ] 名称和 ID 唯一。
- [ ] Button 生成 `lv_button_create()`。
- [ ] LED 生成 `lv_led_create()`。
- [ ] Image 使用正确资源。
- [ ] 动态 Label 可以在运行时更新。

### 视觉

- [ ] 文字没有裁剪。
- [ ] 字体文件和字号正确。
- [ ] 最长数值不溢出。
- [ ] 图标不是近似替代品。
- [ ] Gradient 和 RGB565 色带可接受。
- [ ] JavaScript 与 C/C++ Simulator 均检查过。

### 固件

- [ ] LVGL 小版本与生成工具一致。
- [ ] `lv_conf` 功能开关与生成 API 一致。
- [ ] 图片和字体进入正确存储区域。
- [ ] 触摸输入设备已注册。
- [ ] 显示 flush 正确处理 area、stride 和 D-Cache。
- [ ] 实板运行和触摸验证通过。

## 11. 不要把显示移植问题误判为插件问题

LVGL 9.5 工程最初出现过动态文字逐行倾斜。最终确认是 STM32 显示 flush 忽略 Draw Buffer Stride：

```text
RGB565 13 px 有效数据 = 26 bytes
4-byte 对齐后的 stride = 28 bytes
```

旧代码按 26 bytes 进入下一行，导致每行累积错位。修复后使用：

```c
lv_draw_buf_width_to_stride(width, LV_COLOR_FORMAT_RGB565)
```

该问题属于显示移植层，不是 LVGL 9.5 字体 Bug，也不是 Figma 插件问题。LVGL 9.5 后续已完成主机 10 轮、实板自动检查和人工视觉检查。

推荐排查顺序：

```text
先检查 Figma 源几何
  -> 再检查插件映射和资源
  -> 再检查字体文件与 LVGL 基线
  -> 最后检查 flush、stride、颜色格式和 D-Cache
```

## 12. Git 和目录管理

### 必须保留

- Figma 原始导出快照。
- 规范化脚本。
- GUI Guider `.guiguider` 工程。
- 字体和图片源文件及许可证。
- 生成的关键 C/H 或可重复生成它们的脚本。
- Simulator 和 MDK 的验证记录。

### 不应提交

- Figma Token。
- 本地账号和服务凭据。
- CMake 绝对路径缓存。
- 大量临时截图和调试缓存。
- 仅对当前电脑有效的临时服务状态。

### 推荐提交点

```text
1. 导入前空白工程基线
2. 原始 Figma 导出
3. 规范化规则
4. GUI Guider 视觉确认
5. C Simulator 构建通过
6. MDK 和实板通过
```

## 13. 当前仓库中的相关文件

| 文件 | 作用 |
| --- | --- |
| `README.md` | 仓库入口 |
| `docs/FIGMA_TO_LVGL_WORKFLOW_AND_PITFALLS.md` | 三条路线完整复盘 |
| `docs/FIGMA_TO_GUI_GUIDER_2_0_LVGL_9_4_GUIDE.md` | GUI Guider 阶段的详细问题和验收规范 |
| `tools/reference/figma_plugin_export_71_3.json` | Figma 插件原始导出 |
| `tools/reference/blank_project.guiguider` | 本地 GUI Guider 空白基准 |
| `tools/build_figma_screen.py` | 结构校正、资源校验和项目生成 |
| `guiguider_2.0.guiguider` | GUI Guider 2.0 工程入口 |
| `resources/font/` | 字体资源 |
| `resources/image/` | 图标和图片资源 |
| `generated/` | GUI Guider 生成的 LVGL C/H |

## 14. 给准备使用这条流程的读者

如果你的页面只有少量控件、简单颜色和标准字体，插件可以显著节省时间。

如果页面包含复杂工业仪表、大字号数字、精确图标、渐变光晕和大量交互，请从一开始就接受以下事实：

- Figma 不能代替 LVGL Widget 设计。
- 插件不能代替工程语义校正。
- Simulator 不能代替实板显示端口验证。
- 自动生成不能代替版本、资源和业务层管理。

最可靠的方法不是追求“一键完成”，而是建立一条可检查、可重复、可回滚的流水线。插件负责减少录入工作，GUI 工具负责可视化检查，脚本负责一致性，Git 负责回溯，实板负责最终结论。
