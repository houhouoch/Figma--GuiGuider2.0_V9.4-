# Figma -> GUI Guider 2.0 -> LVGL 9.4 转换复盘与执行规范

> 本文是 GUI Guider 2.0 阶段的详细附录。完整的 LVGL Pro、原生 C 生成器和 GUI Guider 三阶段路线复盘见 [Figma 到 LVGL 的三条路线：实测复盘与避坑指南](FIGMA_TO_LVGL_WORKFLOW_AND_PITFALLS.md)。

> 项目：UDP3900 960 x 240 工业电源仪表界面
> 日期：2026-07-23
> 目标流程：Figma 负责设计，GUI Guider 2.0 负责语义校正、预览和生成 LVGL 9.4 C 代码，MDK 负责最终固件集成。

## 1. 本次结论

这次问题不是单一的“字体不兼容”或“GUI Guider 显示错误”，而是三类问题叠加：

1. **Figma 源图层几何不合法**：文字视觉上能显示，但文本框实际高度小于字号所需高度。
2. **Figma 插件的控件语义推断不可靠**：Line、Button、LED 等对象被错误映射成 Container。
3. **Figma 与 LVGL 的字体行框和渲染规则不同**：大字号需要在目标端校准基线，但不能用它掩盖 Figma 文本框本身的错误。

因此，正确流程不是把插件导出的 JSON 直接当成最终工程，而是：

```text
Figma 规范化设计
    -> 导出结构化 JSON 和图像资源
    -> 检查并修正控件语义、文字框和资源
    -> 合并到 GUI Guider 2.0 的本地 LVGL 9.4 工程
    -> GUI Guider 预览
    -> 生成 C 代码
    -> C/C++ Simulator 验证
    -> MDK 集成
```

## 2. 本次使用的文件

- Figma 文件：`UDP3900 design`
- Figma 整屏节点：`71:3`
- 用户提供的局部节点：`75:18`
- `label_menu` 节点：`74:12`
- GUI Guider 工程：`D:\figma\V2.0\guiguider_2.0\guiguider_2.0\guiguider_2.0.guiguider`
- Figma 原始导出：`tools/reference/figma_plugin_export_71_3.json`
- 本地空白工程基准：`tools/reference/blank_project.guiguider`
- 转换和校验脚本：`tools/build_figma_screen.py`
- 图片资源：`resources/image/`
- 字体资源：`resources/font/`
- GUI Guider 生成代码：`generated/`
- C/C++ 模拟器：`platform/simulator/build/bin/simulator.exe`

项目已经建立 Git 基线，导入前的基准提交为：

```text
677615a chore: baseline GUI Guider 2.0 project before Figma import
```

## 3. 已遇到的问题、根因和处理方法

### 3.1 Figma 画面正常，导入后整体差别很大

**现象**

- Figma 中布局、文字、渐变和图标正常。
- 插件导出的 GUI Guider 工程出现文字移位、裁剪、对象类型错误、部分装饰线变粗或形成多余容器。

**根因**

- 插件只能根据 Figma 图层类型和形状猜测 LVGL 控件类型。
- Figma 的 `FRAME`、`RECTANGLE` 并不等价于 LVGL 的 `container`、`button` 或 `line`。
- 插件导出是结构转换，不是像素级截图复刻，也不会自动理解“这是按钮”“这是 LED”“这是动态读数”。

**正确处理**

- Figma 负责视觉和几何。
- 控件语义必须经过人工规则或转换脚本校正。
- GUI Guider 中的预览只是第一道验收，最终还要验证生成的 LVGL C。

### 3.2 Design Tree 映射错误会直接改变 Project JSON

**现象**

- 1 px 或 2 px 的装饰线被识别为 `container`。
- 菜单按钮、模式按钮和设定值输入区域被识别为 `container`。
- 系统就绪圆点被识别为普通容器。

**根因**

Figma to GUI Guider 插件中的类型下拉框不是显示选项，而是 JSON 生成规则。选择错误后，生成的对象类型、样式字段和 C API 都会改变。

**本项目必须使用的语义映射**

| Figma 节点用途 | GUI Guider / LVGL 类型 | 说明 |
| --- | --- | --- |
| 根画板 `screen_power_console_960x240` | `screen` | 必须保持 960 x 240 |
| 普通面板、无交互分组 | `container` | 只承担布局和背景 |
| 文字 | `label` | 动态值与静态标题要区分 |
| `button_menu` | `button` | 后续需要点击事件 |
| `button_mode_select` | `button` | 后续需要模式选择事件 |
| `input_vset` | `button` | 作为可点击的设定值输入区域 |
| `input_iset_pos` | `button` | 作为可点击的设定值输入区域 |
| `input_iset_neg` | `button` | 作为可点击的设定值输入区域 |
| `indicator_system_ready` | `led` | 需要使用 LED 状态接口控制 |
| 位图或已经确认的图标 | `image` | 不要重新用近似线条绘制 |
| 纯装饰的细直线 | `line` 或无背景对象 | 不应生成带背景、滚动和内边距的容器 |

### 3.3 `label_menu` 被裁剪：根因在 Figma 源图层

**现象**

GUI Guider JavaScript Simulator 中，`MENU` 只显示上半部分或下半部分。

**已确认数据**

- Figma 节点：`74:12`
- 名称：`label_menu`
- 字号：24 px
- Figma 文本框约为：65 x 14 px
- 插件 JSON 又将其导出为 `width=0/content`、`height=0/content`

**根因**

24 px 字体不可能稳定放入 14 px 高的文字框。Figma 画布可以让字形越过文本框继续显示，因此设计时看起来正常；GUI Guider 和 LVGL 会按对象边界裁剪，所以问题在导入后暴露。

**正确修复顺序**

1. 在 Figma 中把 `label_menu` 改成明确的足够高度，例如 65 x 28 px。
2. 或将文本高度设置为 Auto Height，并确认导出工具能保存计算后的实际高度。
3. 明确设置行高，不要只设置字号。
4. 再次导出并检查 JSON 中的宽高不能为 0 或 `content`。

**禁止做法**

- 不要先把它归因于 GUI Guider 字体问题。
- 不要只在 GUI Guider 中用负内边距长期遮盖源图层错误。
- 不要看到 Figma 画布显示完整，就假设文本框尺寸一定正确。

### 3.4 120 px 电压/电流读数的垂直位置不一致

**现象**

- `label_vout` 和 `label_iout` 在 Figma 中位置正确。
- GUI Guider/LVGL 中大字号文字基线偏低，出现顶部或底部裁剪。
- 设置上内边距约 `-20` 后视觉位置恢复。

**根因**

这与 `label_menu` 的源框过小不是同一个问题。大字号读数还受到以下因素影响：

- Figma 与 LVGL 的 ascent、descent 和 line box 计算不同。
- 字体转换后使用的实际 TTF 与 Figma 中的字体版本可能不同。
- GUI Guider 生成的 LVGL 字体包含自身的字形度量。

**当前适配规则**

- `label_vout`：120 px，固定框 414 x 114，目标端 `pad_top=-20`。
- `label_iout`：120 px，固定框 428 x 114，目标端 `pad_top=-20`。
- 当前转换脚本按 `-round(font_size / 6)` 计算大字号基线补偿。

**注意**

负内边距只用于校准 LVGL 字体基线。必须先确认 Figma 文本框尺寸合法，不能用基线补偿修复错误的源框高度。

### 3.5 字体名称相同不代表字体文件相同

**现象**

- Figma 使用某个字体家族，但 GUI Guider 中可能没有该字体。
- 导入后文字宽度、数字间距和上下度量发生变化。

**根因**

Figma 保存的是字体家族和样式引用，不会把字体文件自动嵌入 GUI Guider 工程。即使显示名称接近，不同 TTF 版本的字形和行高也可能不同。

**本项目字体规则**

- `AlibabaPuHuiTi2.0-55Regular` 映射到本地 `AlibabaPuHuiTi1.ttf`。
- IBM Plex Mono/Sans 必须使用 `resources/font/` 中对应的实际文件。
- 大字号数字必须用最终 TTF 在 GUI Guider 生成字体后重新验收。

**验收点**

- JSON 中所有 `text_family` 都能找到本地 TTF。
- 生成目录中存在对应字号的 `lv_font_*` 文件或声明。
- 最长动态字符串不会超出固定文字框。

### 3.6 Figma 文本框被插件导出为 Content Size

**现象**

插件 JSON 中部分 Label 的 `width`、`height` 为 0，单位为 `content`，导致导入后的对齐和裁剪与 Figma 不同。

**根因**

插件用内容自适应替代了 Figma 中的显式边界，丢失了界面设计所依赖的固定几何。

**处理方法**

- 仪表读数、单位、设定值和标题全部使用明确的 px 宽高。
- 不能依赖 `content` 自动尺寸来复刻固定分辨率仪表界面。
- 转换脚本中的 `LABEL_BOXES` 是防御性校正，最终仍应优先修正 Figma 源图层。

### 3.7 图标不能用错误控件或近似图形替代

**现象**

状态栏锁、保护、USB、蜂鸣器和菜单图标曾出现形状错误或风格不一致。

**根因**

- 自动转换把矢量结构拆成了不正确的基础图形。
- 使用了近似图标，而不是 Figma 中的原始资源。
- 直接导出了带 Image Fill 的 Figma Rectangle/Frame，矩形背景也被栅格化进 PNG，
  导致 GUI Guider 中每个图标周围出现深色方块。

**正确处理**

- 优先使用产品工程指定目录中的透明 PNG 原件，不要把 Figma 的图片填充矩形
  整体截图或整节点导出为图标。
- 只有确认目标节点本身就是无背景、带 Alpha 的叶子图像时，才允许从 Figma
  直接导出。
- 图标图层使用 `image`，不要把复杂图标拆成多个 `line/container`。
- 通过 `python tools/prepare_local_assets.py` 将原件等比缩放到透明目标画布，
  再写入 `resources/image/`；按钮背景、边框、光晕和焦点状态仍由 LVGL
  `button` 样式绘制。
- 导出前检查图片的实际像素尺寸、透明通道和 RGB565/RGB565A8 转换结果。
- 必须在深色背景上预览 Alpha 边缘，确认没有矩形底色后再导入 GUI Guider。

### 3.8 静态 Label 与动态 Label 没有区分

**现象**

电压、电流、设定值、输出状态和模式值如果生成成静态文本，后续运行时更新不可靠或接口不符合预期。

**处理方法**

以下对象必须按动态 Label 处理：

- `label_vout`
- `label_iout`
- `label_vset_value`
- `label_iset_pos_value`
- `label_iset_neg_value`
- `label_output_state`
- `label_mode_value`

标题、单位和固定说明文字可以使用静态文本。

### 3.9 直接替换整个 Project JSON 会破坏本地工程配置

**风险**

插件导出的 JSON 可能带有自己的板卡、版本、路径和默认配置。直接覆盖会丢失 GUI Guider 本地工程中的 LVGL 版本、RGB565、模拟器和 `lv_conf` 设置。

**正确处理**

- 以本地 GUI Guider 2.0 空白工程为基准。
- 只从 Figma 导出中合并 UI 图、样式和资源引用。
- 保留本地工程的板卡、960 x 240、16 位色深和 LVGL 9.4 配置。
- 使用脚本生成可重复结果，不要长期手工修改大段 JSON。

### 3.10 打开工程时选错文件

GUI Guider 应打开：

```text
D:\figma\V2.0\guiguider_2.0\guiguider_2.0\guiguider_2.0.guiguider
```

不要选择：

- `generated/` 中的 C 文件。
- 工程目录本身。
- Figma 插件导出的中间 JSON。
- `platform/simulator/` 下的 CMake 文件。

### 3.11 编辑器缩放比例造成“画面太小”的误判

GUI Guider 画布曾显示为 57% 或其他缩放比例。屏幕视觉上变小不代表项目分辨率错误。

检查顺序：

1. 工程设置必须是 960 x 240。
2. Screen 对象必须是 960 x 240。
3. 再检查编辑器右下角的缩放比例。

### 3.12 JavaScript Simulator 不能代替最终 C 验证

**现象**

JavaScript Simulator 可以快速显示，但它与最终生成的 C、字体转换和 LVGL 渲染并不完全等价。

**正确验收顺序**

1. GUI Guider UI 编辑器检查结构。
2. JavaScript Simulator 快速检查布局。
3. 重新生成 C 代码。
4. 编译并运行 C/C++ Simulator。
5. 最终在 STM32 板卡上验证。

### 3.13 工程移动后 CMake 缓存仍指向旧路径

**现象**

第一次构建 C/C++ Simulator 失败，`CMakeCache.txt` 中仍保存旧工程路径：

```text
C:\Users\admin\Documents\GUIGuider-2.0.0\projects\guiguider_2.0
```

而当前工程实际位于：

```text
D:\figma\V2.0\guiguider_2.0\guiguider_2.0
```

**解决方法**

1. 在 GUI Guider 中执行“清除编译目录”。
2. 重新生成 C 代码。
3. 再次构建 C/C++ Simulator。

**注意**

清理编译目录后要检查 `generated/`。本次操作中生成目录也需要重新生成，不能清理后直接编译旧代码。

### 3.14 生成代码成功不等于视觉和语义都正确

本次最终 C/C++ Simulator 构建曾成功到：

```text
[546/546] Linking CXX executable bin\simulator.exe
Build completed successfully
```

这只能证明工程可编译，不能证明以下内容正确：

- 图层尺寸和位置。
- 字体基线和裁剪。
- 按钮是否真的是 Button。
- 状态点是否真的是 LED。
- 图片是否为正确资源。
- 动态值是否可在运行时更新。

## 4. Figma 源文件设计规范

### 4.1 命名规范

- 只使用 ASCII 字母、数字和下划线。
- 使用 `snake_case`。
- 名称必须唯一。
- 名称必须以字母或下划线开头。
- 不使用空格、中文、`-`、`/`、括号或乘号 `x/×` 作为代码对象名的一部分。

推荐前缀：

| 用途 | 前缀 | 示例 |
| --- | --- | --- |
| 屏幕 | `screen_` | `screen_power_console_960x240` |
| 面板 | `panel_` | `panel_setpoints` |
| 按钮 | `button_` | `button_menu` |
| 输入区域 | `input_` | `input_vset` |
| 文本 | `label_` | `label_vout` |
| 单位 | `unit_` | `unit_vout` |
| 图片 | `img_` | `img_status_lock` |
| LED | `indicator_` | `indicator_system_ready` |
| 纯装饰 | `decor_` | `decor_status_divider` |

### 4.2 文字规范

- 每个文本图层必须检查实际 `width`、`height`、字号和行高。
- 文本框高度必须覆盖完整字体行框，不能依赖 Figma 的越界显示。
- 动态数值必须按最长可能字符串设计宽度。
- 固定分辨率仪表优先使用明确 px 尺寸，不依赖导出工具猜测 Auto Size。
- 大字号读数必须使用最终字体文件做一次 LVGL 预览。

### 4.3 几何规范

- 根 Screen 固定为 960 x 240。
- 尽量使用整数坐标和整数尺寸。
- 1 px/2 px 装饰线应单独命名，不与交互容器混合。
- 点击区域和视觉子元素分离：外层 Button，内部 Image/Label。
- 不把多个不同语义对象合并成无法识别的大矢量。

### 4.4 效果规范

LVGL 9.4 可以实现基础渐变、边框、阴影和透明度，但不应依赖以下网页或 Figma 专属效果：

- 背景模糊。
- 多层复杂蒙版。
- 混合模式叠加。
- 复杂实时动画。
- 依赖画布越界才能看到的光晕或文字。

重要装饰效果应在 GUI Guider/LVGL 中验证；复杂但静态的图形可以预渲染成图片。

## 5. 转换脚本必须承担的职责

`tools/build_figma_screen.py` 不是重新设计页面，而是规范化和校验层。它应只做可解释、可重复的转换：

1. 保留本地 GUI Guider 工程的 LVGL 9.4、960 x 240、RGB565 配置。
2. 合并 Figma 的 UI 节点树。
3. 校正插件无法可靠判断的 Widget 类型。
4. 将关键 Label 改为固定像素框。
5. 将运行时数值设为动态文本。
6. 映射并验证本地字体文件。
7. 验证图片路径存在。
8. 验证名称和 ID 唯一。
9. 拒绝非法 C 标识符。
10. 只对确认存在字体度量差异的大字号文本进行基线补偿。

转换脚本不应：

- 修改原始参考 JSON。
- 猜测业务事件和业务逻辑。
- 用大量手工常量掩盖错误的 Figma 源几何。
- 覆盖本地板卡和 LVGL 配置。

## 6. 下次标准执行流程

### 第一步：冻结基线

```bash
git status
git add .
git commit -m "chore: baseline before Figma import"
```

确保可以随时回到导入前状态。

### 第二步：检查 Figma 源画板

- Screen 是否为 960 x 240。
- 所有图层是否按代码规范命名。
- 所有文字框是否有足够高度。
- 图标是否为可导出的 Image/SVG，而不是模糊的复合形状。
- 按钮、输入区、LED 和装饰线的语义是否明确。

### 第三步：导出结构化数据

- 保存原始导出到 `tools/reference/`。
- 原始文件只作为输入证据，不直接手改。
- 检查 Design Tree 类型映射后再 Convert/Export。

### 第四步：运行规范化脚本

```bash
python tools/build_figma_screen.py
```

脚本必须完成版本、分辨率、名称、资源、字体和控件类型校验；任何断言失败都先修源数据，不继续导入。

### 第五步：打开正确工程

打开 `guiguider_2.0.guiguider`，检查：

- Screen 尺寸。
- 文字框边界。
- 控件树类型。
- 图标。
- 动态 Label。
- 颜色和渐变。

### 第六步：生成并验证 C

1. GUI Guider 中重新生成 C。
2. 检查生成代码使用正确 API：
   - Button：`lv_button_create`
   - LED：`lv_led_create`
   - Image：`lv_image_create`
   - Label：`lv_label_create`
3. 构建 C/C++ Simulator。
4. 运行 `platform/simulator/build/bin/simulator.exe`。
5. 对照 Figma 逐项截图检查。

### 第七步：再进入 MDK

只有模拟器通过后才把生成代码、字体、图片和事件接口接入 STM32 工程。不要把 Figma 导出后的第一次结果直接放入 MDK 调试。

## 7. 导入前验收清单

### Figma

- [ ] 根画板为 960 x 240。
- [ ] 图层命名是唯一、合法的 C 标识符。
- [ ] 24 px 文字框高度不再只有 14 px。
- [ ] `label_menu` 使用足够高度或可验证的 Auto Height。
- [ ] 大字号读数的文本框能容纳完整字形。
- [ ] 动态值按最长字符串预留宽度。
- [ ] 图标使用原始资源。
- [ ] 细线、按钮、LED 的图层语义明确。

### JSON / 转换层

- [ ] LVGL 版本为 9.4.0。
- [ ] 色深为 16 bit / RGB565。
- [ ] Screen 为 960 x 240。
- [ ] 关键 Label 不使用 `0/content` 尺寸。
- [ ] 按钮没有被映射为 Container。
- [ ] LED 没有被映射为 Container。
- [ ] 图片和字体文件全部存在。
- [ ] 动态 Label 的 `static_text` 为 false。
- [ ] 节点名称和 ID 无重复。

### GUI Guider / LVGL

- [ ] UI 编辑器无裁剪和错位。
- [ ] JavaScript Simulator 只作为快速检查。
- [ ] 重新生成 C 后无旧文件残留。
- [ ] C/C++ Simulator 编译成功。
- [ ] C/C++ Simulator 与 Figma 视觉对照通过。
- [ ] 按钮、LED 和动态 Label 的生成 API 正确。

## 8. 裁剪问题快速判断

```text
文字被裁剪
  |
  +-- Figma 文本框高度 < 字号/行高？
  |     +-- 是：先修 Figma；这是源数据错误
  |
  +-- JSON 宽高为 0/content？
  |     +-- 是：恢复显式 px 尺寸
  |
  +-- GUI Guider 使用的 TTF 与 Figma 不同？
  |     +-- 是：统一实际字体文件
  |
  +-- 只有 LVGL 中基线偏移？
        +-- 是：在源框合法后再做 pad_top 等目标端校准
```

## 9. 本次最重要的经验

1. **先检查 Figma 图层的真实边界，不要只看画布上的视觉结果。**
2. **插件 Design Tree 的类型映射会直接改变 JSON 和生成的 C。**
3. **Figma 负责视觉，GUI Guider 负责 LVGL 控件语义，两者之间必须有校验层。**
4. **字体文件、文字框和字体基线是三个独立问题，必须分别判断。**
5. **JavaScript 预览不等于最终 LVGL C；C/C++ Simulator 才是进入 MDK 前的验收基准。**
6. **工程移动后先清理 CMake 缓存，再重新生成 C。**
7. **所有自动修正必须进入脚本和文档，不能只留在 GUI Guider 的一次手工调整中。**

## 10. 当前待处理项

本次编写文档时按要求没有继续修改 Figma 或 GUI Guider 页面。下一次继续时，第一项应是：

- 在 Figma 中修正 `label_menu` 节点 `74:12` 的真实文本框高度，并重新导出验证。

修正后，应确认 JSON 不再把该对象退化为不可控的 `0/content` 尺寸，再决定是否仍需要目标端基线补偿。
