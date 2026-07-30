#!/usr/bin/env python3
"""Compare two versioned Figma SourceNode manifests before GUI Guider sync."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import sync_completed_figma_to_guiguider as sync


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class NodeRecord:
    page_id: str
    page_name: str
    target_name: str
    figma_id: str
    name: str
    node_type: str
    semantic_type: str
    parent_id: str | None
    order: int
    path: str
    x: float
    y: float
    width: float
    height: float
    fill: Any
    stroke: Any
    stroke_width: float
    corner_radius: float
    opacity: int
    visible: bool
    clips_content: bool
    text: str | None
    font_size: float | None
    font_family: str | None
    font_style: str | None
    text_align: str | None
    line_height: float | None
    image_hash: str | None
    image_reference: str | None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalized_source_type(value: str) -> str:
    aliases = {
        "rounded-rectangle": "rectangle",
        "component-set": "component",
    }
    return aliases.get(value.lower(), value.lower())


def normalized_paint(
    explicit: Any,
    fallback_color: Any,
    fallback_opacity: Any,
) -> tuple[str, int] | None:
    if isinstance(explicit, (list, tuple)) and explicit:
        color = str(explicit[0]).lower()
        opacity = int(explicit[1]) if len(explicit) > 1 else 255
        return color, opacity
    if fallback_color:
        return str(fallback_color).lower(), int(fallback_opacity or 0)
    return None


def normalized_image_hash(image_hash: str | None, asset_url: str | None) -> str | None:
    if image_hash:
        return image_hash.lower()
    if asset_url:
        match = re.search(r"([0-9a-fA-F]{40})(?:\.[A-Za-z0-9]+)?(?:$|\?)", asset_url)
        if match:
            return match.group(1).lower()
    return None


def source_records(
    index_path: Path,
) -> tuple[dict[str, NodeRecord], dict[str, dict[str, Any]]]:
    index = load_json(index_path)
    records: dict[str, NodeRecord] = {}
    pages: dict[str, dict[str, Any]] = {}
    for spec in index["roots"]:
        pages[spec["id"]] = spec
        source_dir = index_path.parent / spec["directory"]
        raw_path = source_dir / "raw_context.txt"
        if raw_path.is_file():
            _, metadata, tsx, _ = sync.extract_sections(
                raw_path.read_text(encoding="utf-8")
            )
            supplements = sorted(source_dir.glob("*_supplement.tsx"))
            if supplements:
                tsx = "\n".join(
                    [tsx, *[path.read_text(encoding="utf-8") for path in supplements]]
                )
            root = sync.parse_source_tree(metadata, tsx)
        else:
            root = sync.parse_compact_tree(
                source_dir,
                sync.legacy_asset_urls(spec),
            )

        def visit(node: sync.SourceNode, path: str, order: int) -> None:
            semantic_type = sync.classify(node, root)
            visual = (
                sync.label_style(node)[sync.MAIN_STYLE]
                if semantic_type == "label"
                else sync.base_visual_style(node)[sync.MAIN_STYLE]
            )
            is_label = semantic_type == "label"
            fill = normalized_paint(
                node.fill,
                visual.get("text_color") if is_label else visual.get("bg_color"),
                visual.get("text_opa") if is_label else visual.get("bg_opa"),
            )
            stroke = normalized_paint(
                node.stroke,
                visual.get("border_color"),
                visual.get("border_opa"),
            )
            records[node.id] = NodeRecord(
                page_id=spec["id"],
                page_name=spec["name"],
                target_name=spec["target_name"],
                figma_id=node.id,
                name=node.name,
                node_type=normalized_source_type(node.tag),
                semantic_type=semantic_type,
                parent_id=node.parent.id if node.parent else None,
                order=order,
                path=path,
                x=node.x,
                y=node.y,
                width=node.width,
                height=node.height,
                fill=fill,
                stroke=stroke,
                stroke_width=float(visual.get("border_width") or 0),
                corner_radius=float(visual.get("radius") or 0),
                opacity=int(visual.get("opa") or 0),
                visible=not node.hidden,
                clips_content=bool(visual.get("clip_corner", 0)),
                text=node.text if is_label else None,
                font_size=(
                    float(visual.get("text_size")) if visual.get("text_size") else None
                )
                if is_label
                else None,
                font_family=visual.get("text_family") if is_label else None,
                font_style=None,
                text_align=visual.get("text_align") if is_label else None,
                line_height=None,
                image_hash=normalized_image_hash(node.image_hash, node.asset_url),
                image_reference=None,
            )
            for child_order, child in enumerate(node.children):
                visit(child, f"{path}/{child.name or child.id}", child_order)

        visit(root, root.name or root.id, 0)
    return records, pages


def walk_objects(nodes: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from walk_objects(node.get("children", []) or [])


def project_mapping(project_path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    project = load_json(project_path)
    mapping = {
        node["figma_id"]: {
            "object_id": node.get("id"),
            "object_name": node.get("name"),
            "object_type": node.get("type"),
        }
        for node in walk_objects(project["UI"]["screen_list"])
        if node.get("figma_id")
    }
    business_payload = json.dumps(
        {
            "event_list": project["UI"].get("event_list"),
            "variable_setting": project["UI"].get("variable_setting"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return mapping, business_payload


def add_unique_matches(
    old_nodes: dict[str, NodeRecord],
    new_nodes: dict[str, NodeRecord],
    matched: dict[str, tuple[str, str, float]],
    old_key,
    new_key,
    reason: str,
    confidence: float,
) -> None:
    old_groups: dict[Any, list[str]] = defaultdict(list)
    new_groups: dict[Any, list[str]] = defaultdict(list)
    paired_old = set(matched)
    paired_new = {row[0] for row in matched.values()}
    for node_id, node in old_nodes.items():
        if node_id not in paired_old:
            old_groups[old_key(node)].append(node_id)
    for node_id, node in new_nodes.items():
        if node_id not in paired_new:
            new_groups[new_key(node)].append(node_id)
    for key in sorted(set(old_groups) & set(new_groups), key=str):
        if len(old_groups[key]) == len(new_groups[key]) == 1:
            matched[old_groups[key][0]] = (
                new_groups[key][0],
                reason,
                confidence,
            )


def change_entry(
    category: str,
    old: NodeRecord | None,
    new: NodeRecord | None,
    *,
    detail: dict[str, Any],
    recommendation: str,
    confidence: float,
    mapping: dict[str, dict[str, Any]],
    business_payload: str,
) -> dict[str, Any]:
    old_mapping = mapping.get(old.figma_id) if old else None
    business_impact = bool(
        old_mapping
        and any(
            token and str(token) in business_payload
            for token in (old_mapping.get("object_id"), old_mapping.get("object_name"))
        )
    )
    return {
        "category": category,
        "page_name": (new or old).page_name if (new or old) else None,
        "old_figma_id": old.figma_id if old else None,
        "new_figma_id": new.figma_id if new else None,
        "old_name": old.name if old else None,
        "new_name": new.name if new else None,
        "old_path": old.path if old else None,
        "new_path": new.path if new else None,
        "detail": detail,
        "recommended_guiguider_action": recommendation,
        "match_confidence": round(confidence, 3),
        "may_affect_event_focus_or_business_code": business_impact
        or category
        in {
            "page_deleted",
            "node_deleted",
            "node_id_changed",
            "node_renamed",
            "parent_changed",
            "semantic_or_type_changed",
            "identity_uncertain",
        },
        "existing_object_mapping": old_mapping,
    }


def scroll_extent(nodes: dict[str, NodeRecord], page_id: str) -> float:
    page_nodes = [node for node in nodes.values() if node.page_id == page_id]
    if not page_nodes:
        return 0
    by_id = {node.figma_id: node for node in page_nodes}

    def absolute_bottom(node: NodeRecord) -> float:
        y = node.y
        parent_id = node.parent_id
        seen: set[str] = set()
        while parent_id and parent_id in by_id and parent_id not in seen:
            seen.add(parent_id)
            parent = by_id[parent_id]
            y += parent.y
            parent_id = parent.parent_id
        return y + node.height

    return max(absolute_bottom(node) for node in page_nodes)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Manifest {report['old_manifest_version']} -> {report['new_manifest_version']} 语义差异",
        "",
        f"- 旧 Manifest：`{report['old_manifest']}`",
        f"- 新 Manifest：`{report['new_manifest']}`",
        f"- 自动匹配节点：{report['summary']['matched_nodes']}",
        f"- 身份不确定节点：{report['summary']['identity_uncertain']}",
        f"- 控件类型变化：{report['summary']['semantic_or_type_changed']}",
        f"- 可能影响事件/焦点/业务代码：{report['summary']['business_impact_changes']}",
        "",
        "## 分类统计",
        "",
        "| 变化类型 | 数量 |",
        "|---|---:|",
    ]
    for category, count in sorted(report["summary"]["by_category"].items()):
        lines.append(f"| `{category}` | {count} |")
    lines.extend(["", "## 变化明细", ""])
    for item in report["changes"]:
        detail = json.dumps(item["detail"], ensure_ascii=False, sort_keys=True)
        lines.extend(
            [
                f"### {item['category']} - {item['page_name']}",
                "",
                f"- ID：`{item['old_figma_id']}` -> `{item['new_figma_id']}`",
                f"- 名称：`{item['old_name']}` -> `{item['new_name']}`",
                f"- 路径：`{item['old_path']}` -> `{item['new_path']}`",
                f"- 置信度：{item['match_confidence']}",
                f"- 业务影响：{item['may_affect_event_focus_or_business_code']}",
                f"- 建议：{item['recommended_guiguider_action']}",
                f"- 详情：`{detail}`",
                "",
            ]
        )
    if not report["changes"]:
        lines.append("没有检测到语义变化。")
    return "\n".join(lines).rstrip() + "\n"


def field_ownership(project_path: Path) -> str:
    project = load_json(project_path)
    object_keys: dict[str, set[str]] = defaultdict(set)
    for node in walk_objects(project["UI"]["screen_list"]):
        object_keys[str(node.get("type"))].update(node)
    types = ", ".join(
        f"`{kind}`: {', '.join(f'`{key}`' for key in sorted(keys))}"
        for kind, keys in sorted(object_keys.items())
    )
    return f"""# GUI Guider 字段所有权

本报告按当前 `{project_path.name}` 的实际 JSON Schema 制定，不是通用猜测。

## 实际工程结构

- 根字段：{", ".join(f"`{key}`" for key in project)}
- `projectSettings`：{", ".join(f"`{key}`" for key in project["projectSettings"])}
- `UI`：{", ".join(f"`{key}`" for key in project["UI"])}
- 当前对象类型与实际字段：{types}
- 当前 `UI.event_list` 条目数：{len(project["UI"].get("event_list") or {})}
- 当前 `UI.variable_setting` 条目数：{len(project["UI"].get("variable_setting") or {})}

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
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-index", type=Path, required=True)
    parser.add_argument("--new-index", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    old_nodes, old_pages = source_records(args.old_index)
    new_nodes, new_pages = source_records(args.new_index)
    mapping, business_payload = project_mapping(args.project)
    changes: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    matches: dict[str, tuple[str, str, float]] = {
        node_id: (node_id, "same_figma_id", 1.0)
        for node_id in set(old_nodes) & set(new_nodes)
    }
    add_unique_matches(
        old_nodes,
        new_nodes,
        matches,
        lambda node: (node.target_name, node.path, node.node_type),
        lambda node: (node.target_name, node.path, node.node_type),
        "stable_semantic_path",
        0.95,
    )
    add_unique_matches(
        old_nodes,
        new_nodes,
        matches,
        lambda node: (
            node.target_name,
            node.name,
            node.node_type,
            old_nodes[node.parent_id].name if node.parent_id in old_nodes else None,
        ),
        lambda node: (
            node.target_name,
            node.name,
            node.node_type,
            new_nodes[node.parent_id].name if node.parent_id in new_nodes else None,
        ),
        "unique_name_type_parent",
        0.88,
    )

    old_page_targets = {row["target_name"]: row for row in old_pages.values()}
    new_page_targets = {row["target_name"]: row for row in new_pages.values()}
    for target in sorted(set(new_page_targets) - set(old_page_targets)):
        page = new_page_targets[target]
        node = new_nodes[page["id"]]
        changes.append(
            change_entry(
                "page_added",
                None,
                node,
                detail={"target_name": target},
                recommendation="新增候选 screen；不自动添加事件或 focus",
                confidence=1.0,
                mapping=mapping,
                business_payload=business_payload,
            )
        )
    for target in sorted(set(old_page_targets) - set(new_page_targets)):
        page = old_page_targets[target]
        node = old_nodes[page["id"]]
        changes.append(
            change_entry(
                "page_deleted",
                node,
                None,
                detail={"target_name": target},
                recommendation="先检查事件和业务引用；存在引用时阻断删除",
                confidence=1.0,
                mapping=mapping,
                business_payload=business_payload,
            )
        )

    new_to_old = {new_id: old_id for old_id, (new_id, _, _) in matches.items()}
    for old_id, (new_id, reason, confidence) in sorted(matches.items()):
        old = old_nodes[old_id]
        new = new_nodes[new_id]
        if old_id != new_id:
            changes.append(
                change_entry(
                    "node_id_changed",
                    old,
                    new,
                    detail={"match_reason": reason, "alias": f"{old_id}->{new_id}"},
                    recommendation="保留原 GUI Guider object name/ID，记录 Figma ID 别名",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.name != new.name:
            changes.append(
                change_entry(
                    "node_renamed",
                    old,
                    new,
                    detail={},
                    recommendation="保留稳定 object name；仅更新 Figma 显示名称映射",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        expected_new_parent = (
            matches.get(old.parent_id, (None, "", 0))[0] if old.parent_id else None
        )
        if expected_new_parent != new.parent_id:
            changes.append(
                change_entry(
                    "parent_changed",
                    old,
                    new,
                    detail={
                        "old_parent": old.parent_id,
                        "new_parent": new.parent_id,
                        "mapped_old_parent": expected_new_parent,
                    },
                    recommendation="重新计算相对坐标并检查裁剪、滚动和图层顺序",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.order != new.order:
            changes.append(
                change_entry(
                    "layer_order_changed",
                    old,
                    new,
                    detail={"old": old.order, "new": new.order},
                    recommendation="按新 SourceNode 顺序重建候选 children",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.semantic_type != new.semantic_type:
            changes.append(
                change_entry(
                    "semantic_or_type_changed",
                    old,
                    new,
                    detail={
                        "old": [old.node_type, old.semantic_type],
                        "new": [new.node_type, new.semantic_type],
                    },
                    recommendation="检查事件、对象引用和资源后再改变 GUI Guider type",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        old_geometry = (old.x, old.y, old.width, old.height)
        new_geometry = (new.x, new.y, new.width, new.height)
        if old_geometry != new_geometry:
            changes.append(
                change_entry(
                    "geometry_changed",
                    old,
                    new,
                    detail={"old": old_geometry, "new": new_geometry},
                    recommendation="更新候选几何并验证最终绝对坐标",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        old_style = (
            old.fill,
            old.stroke,
            old.stroke_width,
            old.corner_radius,
            old.opacity,
            old.clips_content,
        )
        new_style = (
            new.fill,
            new.stroke,
            new.stroke_width,
            new.corner_radius,
            new.opacity,
            new.clips_content,
        )
        if old_style != new_style:
            changes.append(
                change_entry(
                    "style_changed",
                    old,
                    new,
                    detail={"old": old_style, "new": new_style},
                    recommendation="更新 Figma 管理的视觉字段",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.semantic_type == "label" and old.text != new.text:
            changes.append(
                change_entry(
                    "text_changed",
                    old,
                    new,
                    detail={"old": old.text, "new": new.text},
                    recommendation="静态文本可同步；动态数值需保留业务绑定",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        old_font = (
            old.font_size,
            old.font_family,
            old.font_style,
            old.text_align,
            old.line_height,
        )
        new_font = (
            new.font_size,
            new.font_family,
            new.font_style,
            new.text_align,
            new.line_height,
        )
        if old_font != new_font:
            changes.append(
                change_entry(
                    "font_or_size_changed",
                    old,
                    new,
                    detail={"old": old_font, "new": new_font},
                    recommendation="按实际字号映射 AlibabaPuHuiTi2.0.ttf 并检查基线裁剪",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.image_hash != new.image_hash:
            changes.append(
                change_entry(
                    "image_resource_changed",
                    old,
                    new,
                    detail={
                        "old": [old.image_hash, old.image_reference],
                        "new": [new.image_hash, new.image_reference],
                    },
                    recommendation="重新执行本地透明原件优先匹配和 SHA-256 去重",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )
        if old.visible != new.visible:
            changes.append(
                change_entry(
                    "visibility_changed",
                    old,
                    new,
                    detail={"old": old.visible, "new": new.visible},
                    recommendation="更新初始 HIDDEN 状态，保留运行时显隐语义",
                    confidence=confidence,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )

    unmatched_old = set(old_nodes) - set(matches)
    unmatched_new = set(new_nodes) - set(new_to_old)
    for old_id in sorted(unmatched_old):
        old = old_nodes[old_id]
        candidates = [
            node
            for node in new_nodes.values()
            if node.figma_id in unmatched_new
            and node.target_name == old.target_name
            and node.name == old.name
        ]
        if candidates:
            warning = change_entry(
                "identity_uncertain",
                old,
                candidates[0],
                detail={"candidate_ids": [node.figma_id for node in candidates]},
                recommendation="人工确认身份；禁止自动更新正式工程",
                confidence=0.5 if len(candidates) == 1 else 0.25,
                mapping=mapping,
                business_payload=business_payload,
            )
            changes.append(warning)
            warnings.append({"severity": "blocking", **warning})
        else:
            item = change_entry(
                "node_deleted",
                old,
                None,
                detail={},
                recommendation="检查业务引用；无引用时才从候选 Tree 删除",
                confidence=1.0,
                mapping=mapping,
                business_payload=business_payload,
            )
            changes.append(item)
            if item["may_affect_event_focus_or_business_code"]:
                warnings.append({"severity": "blocking", **item})
    for new_id in sorted(unmatched_new):
        new = new_nodes[new_id]
        changes.append(
            change_entry(
                "node_added",
                None,
                new,
                detail={},
                recommendation="按明确语义映射；不确定时使用 container/decor 且不加事件",
                confidence=1.0,
                mapping=mapping,
                business_payload=business_payload,
            )
        )

    for target in sorted(set(old_page_targets) & set(new_page_targets)):
        old_page = old_page_targets[target]
        new_page = new_page_targets[target]
        old_extent = scroll_extent(old_nodes, old_page["id"])
        new_extent = scroll_extent(new_nodes, new_page["id"])
        if old_extent != new_extent:
            changes.append(
                change_entry(
                    "scroll_range_changed",
                    old_nodes[old_page["id"]],
                    new_nodes[new_page["id"]],
                    detail={"old_extent": old_extent, "new_extent": new_extent},
                    recommendation="重新计算滚动范围并保持 scrollbar mode off",
                    confidence=1.0,
                    mapping=mapping,
                    business_payload=business_payload,
                )
            )

    for item in changes:
        if item["category"] in {"identity_uncertain", "semantic_or_type_changed"}:
            if not any(
                warning.get("category") == item["category"]
                and warning.get("old_figma_id") == item["old_figma_id"]
                for warning in warnings
            ):
                warnings.append({"severity": "blocking", **item})

    aliases = [
        {
            "old_node_id": old_id,
            "new_node_id": new_id,
            "reason": reason,
            "confidence": confidence,
            "object_mapping": mapping.get(old_id),
        }
        for old_id, (new_id, reason, confidence) in sorted(matches.items())
        if old_id != new_id
    ]
    mapping_changes = [
        {
            "old_figma_id": old_id,
            "new_figma_id": new_id,
            "match_reason": reason,
            "confidence": confidence,
            "existing": mapping.get(old_id),
            "recommended_object_name": (
                mapping.get(old_id, {}).get("object_name")
                or sync.sanitize(new_nodes[new_id].name)
            ),
        }
        for old_id, (new_id, reason, confidence) in sorted(matches.items())
    ]
    by_category: dict[str, int] = defaultdict(int)
    for item in changes:
        by_category[item["category"]] += 1
    report = {
        "schema_version": "figma-manifest-semantic-diff/v1",
        "old_manifest": str(args.old_index.resolve()),
        "new_manifest": str(args.new_index.resolve()),
        "old_manifest_version": load_json(args.old_index).get("snapshot_version"),
        "new_manifest_version": load_json(args.new_index).get("snapshot_version"),
        "identity_policy": [
            "explicit_saved_mapping",
            "same_figma_node_id",
            "stable_semantic_name_and_parent_path",
            "same_component_or_control_semantics",
            "unique_name_type_parent",
            "geometry_and_style_are_auxiliary_only",
        ],
        "summary": {
            "old_pages": len(old_pages),
            "new_pages": len(new_pages),
            "old_nodes": len(old_nodes),
            "new_nodes": len(new_nodes),
            "matched_nodes": len(matches),
            "identity_uncertain": by_category["identity_uncertain"],
            "semantic_or_type_changed": by_category["semantic_or_type_changed"],
            "business_impact_changes": sum(
                1
                for item in changes
                if item["may_affect_event_focus_or_business_code"]
            ),
            "by_category": dict(sorted(by_category.items())),
        },
        "aliases": aliases,
        "changes": changes,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest_diff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (args.output_dir / "manifest_diff.md").write_text(
        render_markdown(report),
        encoding="utf-8",
        newline="\n",
    )
    (args.output_dir / "object_mapping_changes.json").write_text(
        json.dumps(
            {
                "schema_version": "figma-object-mapping-changes/v1",
                "aliases": aliases,
                "mappings": mapping_changes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (args.output_dir / "warnings.json").write_text(
        json.dumps(
            {
                "schema_version": "figma-controlled-sync-warnings/v1",
                "blocking_count": sum(
                    1 for warning in warnings if warning["severity"] == "blocking"
                ),
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (args.output_dir / "field_ownership.md").write_text(
        field_ownership(args.project),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"REPORT_DIR={args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
