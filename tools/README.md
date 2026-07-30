# Tools / 工具

[English](#english) | [中文](#中文)

## 中文

核心流程工具：

- `refresh_figma_local_snapshot.py`：抓取并版本化 Figma 快照。
- `compare_figma_manifests.py`：比较旧、新 Manifest。
- `sync_completed_figma_to_guiguider.py`：生成独立候选工程。
- `validate_figma_guider_sync.py`：结构、资源、字段和视觉验证。
- `prepare_guiguider_review_workspace.py`：创建隔离审核工程。
- `verify_guiguider_roundtrip.py`：验证 GUI Guider 打开/保存往返。
- `promote_guiguider_candidate.py`：经批准后备份并晋升。
- `audit_guiguider_typography.py`：逐文本字体与几何审计。
- `prepare_local_project.py`：从公开模板生成具有独立项目身份的本机可打开工程；默认拒绝覆盖已有工程。
- `validate_repository.py`：GitHub 仓库自检。

其余脚本保留了本项目具体页面的历史修复方法，用于复现和复盘。执行任何写入脚本前，先在候选副本上运行，并检查其默认输入/输出。

## English

Core pipeline tools:

- `refresh_figma_local_snapshot.py`: capture a versioned Figma snapshot.
- `compare_figma_manifests.py`: compare old and new manifests.
- `sync_completed_figma_to_guiguider.py`: generate an isolated candidate.
- `validate_figma_guider_sync.py`: validate structure, resources and visuals.
- `prepare_guiguider_review_workspace.py`: create an isolated review project.
- `verify_guiguider_roundtrip.py`: verify an editor open/save round trip.
- `promote_guiguider_candidate.py`: back up and promote an approved candidate.
- `audit_guiguider_typography.py`: audit typography and geometry.
- `prepare_local_project.py`: create a machine-local project with an independent identity; existing output is protected by default.
- `validate_repository.py`: validate the public repository.

Other scripts preserve project-specific repair history. Run write-capable tools only against an isolated candidate and inspect their defaults first.
