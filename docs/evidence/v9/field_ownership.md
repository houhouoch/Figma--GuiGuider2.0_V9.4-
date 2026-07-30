# GUI Guider 字段所有权

本报告按当前 `guiguider_2.0.guiguider` 的实际 JSON Schema 制定，不是通用猜测。

## 实际工程结构

- 根字段：`projectId`, `projectName`, `projectPath`, `version`, `toolVendor`, `createDate`, `createVersion`, `lastModified`, `description`, `metadata`, `projectSettings`, `lvConf`, `UI`
- `projectSettings`：`lvglVersion`, `width`, `height`, `targetConfig`, `imageConfig`, `fontConfig`
- `UI`：`variable_setting`, `event_list`, `screen_list`
- 当前对象类型与实际字段：`button`: `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `style`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`, `container`: `add_flag`, `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `remove_flag`, `scrollbar_mode`, `style`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`, `image`: `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `src`, `style`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`, `label`: `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `static_text`, `style`, `text`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`, `layer_bottom`: `children`, `id`, `name`, `remove_flag`, `scrollbar_mode`, `type`, `layer_sys`: `children`, `id`, `name`, `remove_flag`, `scrollbar_mode`, `type`, `layer_top`: `children`, `id`, `name`, `remove_flag`, `scrollbar_mode`, `type`, `led`: `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `style`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`, `screen`: `children`, `default_screen`, `figma_id`, `id`, `name`, `remove_flag`, `scrollbar_mode`, `style`, `type`, `switch`: `align`, `children`, `figma_id`, `height`, `height_unit`, `id`, `name`, `style`, `type`, `width`, `width_unit`, `x`, `x_unit`, `y`, `y_unit`
- 当前 `UI.event_list` 条目数：0
- 当前 `UI.variable_setting` 条目数：0

## 所有权规则

| 字段/区域 | 所有者 | 同步策略 |
|---|---|---|
| `projectId/projectName/projectPath/version/metadata` | GUI Guider 工程 | 从正式工程完整保留 |
| `projectSettings/lvConf` | GUI Guider 工程 | 完整保留 LVGL 9.4、960x240、RGB565、板卡、模拟器和资源配置 |
| `UI.variable_setting/UI.event_list` | 手工业务层/GUI Guider | 完整保留，不由 Figma 重建 |
| `figma_id` | 同步映射层 | 作为显式身份映射；ID 变化必须记录别名或阻断 |
| `id/name` | GUI Guider 身份层 | 已有稳定对象优先保留；新增对象才生成稳定 ID/合法 C 名称 |
| `type` | Figma 语义提示 + GUI Guider Schema | 类型变化需检查事件、资源和业务引用，不静默覆盖 |
| `children` 与子对象顺序 | Figma 视觉层 | 按 SourceNode Tree 重建，但保留手工业务字段 |
| `x/y/width/height/align` | Figma 视觉层 | 使用相对坐标和父子层级；换父节点时重新计算 |
| `style` 中 fill/stroke/radius/opacity/text | Figma 视觉层 | 更新受支持的视觉字段；GUI Guider 必需字段继续补齐 |
| `text/static_text` | Figma 视觉层 + 运行时业务层 | 静态标签同步；动态值不得用 Figma 示例值覆盖业务绑定 |
| `src` | 资源映射层 | 本地透明原件优先，SHA-256 去重，相对路径写入 |
| 事件、focus group、回调、自定义引用 | 手工业务层 | 只保留和校验，不从 Figma 自动生成 |
| `scrollbar_mode/remove_flag/add_flag` | 同步策略层 | 根据内容范围和 visible 状态计算，滚动条保持关闭 |

## 冲突策略

1. 身份、类型、删除、事件引用冲突一律写入 `warnings.json`。
2. 有现成稳定映射时，Figma 改名不自动改 GUI Guider object name。
3. Figma 已删除但仍被业务字段引用的对象暂不删除候选对象，并标记 blocking。
4. 动态文本、事件和运行时状态不接受 Figma 示例值覆盖。
