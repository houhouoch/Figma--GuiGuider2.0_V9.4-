---
title: GUI Guider 2.0 重复 projectId 会打开旧工程
tags:
  - GUI-Guider
  - projectId
  - 调试
  - 工程隔离
status: verified
date: 2026-07-30
---

# GUI Guider 2.0 重复 projectId 会打开旧工程

## 结论

复制 `.guiguider` 文件时，仅修改文件名、目录或 `projectPath` 不足以形成独立
工程。若新旧工程保留相同 `projectId`，GUI Guider 2.0 的最近工程和单实例
逻辑可能继续关联旧路径，表现为每次打开旧工程，或者删除控件后重新出现。

## 识别方式

先排除文件权限，再比较：

```text
projectId
projectName
projectPath
```

必要时检查：

```text
%APPDATA%\GUIGuider\2.0.0\project_history.json
```

GUI Guider 进程启动或收到文件路径，不等于编辑器内部已经加载目标工程。应核对
窗口中的项目名和页面树。

## 修复原则

1. 正式、候选、审核和本地克隆必须使用不同 `projectId`。
2. 本地工程名必须能直观看出身份。
3. 本地准备脚本默认不得覆盖已有工程。
4. 修改后的人工验证必须包含：保存、关闭、重新打开同一文件。
5. 只有明确放弃本地修改时才能执行强制重建。

## 已验证证据

- 新旧文件曾共同使用 `project-MRWWUBKD5NV0`；
- GUI Guider 历史记录和实际进程落到旧正式路径；
- 文件不是只读，ACL 和读写句柄正常；
- 新脚本会按输出路径生成独立 ID；
- 不同目录生成不同 ID；
- 重复准备默认被阻止；
- 自动测试、项目审计和 GitHub Actions 均通过。

## 待确认

新独立 ID 工程中的“删除控件、保存、关闭、重开后仍保持删除”需要完成一次
人工验证，才可将保存持久化标记为完全闭环。
