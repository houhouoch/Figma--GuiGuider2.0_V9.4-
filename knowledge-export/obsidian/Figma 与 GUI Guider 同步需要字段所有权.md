---
title: Figma 与 GUI Guider 同步需要字段所有权
tags:
  - Figma
  - GUI-Guider
  - 字段所有权
  - 生成代码
status: verified
date: 2026-07-30
---

# Figma 与 GUI Guider 同步需要字段所有权

## 结论

Figma 只应更新经过审核的视觉字段，不能成为 GUI Guider 项目配置、稳定对象身份或业务字段的所有者。

## 推荐所有权

| 数据 | 所有者 |
|---|---|
| 父子层级、图层顺序、几何、视觉样式 | Figma |
| `projectId/projectName/projectPath/projectSettings/lvConf` | 正式 GUI Guider 工程 |
| 既有对象 `id/name` | GUI Guider 身份层 |
| `figma_id` | 同步映射层 |
| 事件、变量、焦点、回调、动态状态 | 业务层 |
| 图片、字体及其内容哈希 | 资源层 |

## 冲突处理

- 已有 Figma ID 匹配时保留稳定 GUI Guider ID 和名称。
- 控件类型变化必须阻断并人工审核。
- Figma 删除但业务仍引用的对象不能静默删除。
- Figma 示例文本不能覆盖运行时动态值。
- 全量同步不能替代单页面直接修复。

## 已验证证据

受控同步测试已经覆盖：

- 父子树重建；
- 名称分配器保留既有所有者；
- 对象身份和业务字段保持；
- 已审核透明资源优先。
