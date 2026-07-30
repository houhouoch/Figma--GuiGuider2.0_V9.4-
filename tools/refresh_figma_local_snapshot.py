#!/usr/bin/env python3
"""Refresh the read-only Figma snapshot directly through the local MCP API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import threading
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_INDEX = (
    ROOT / "manifests" / "v9_all_20260729_context" / "index.json"
)
MCP_URL = "http://localhost:3845/mcp"
PROTOCOL_VERSION = "2025-03-26"
FIGMA_FILE_KEY = "Un9Yk92UDIlh910yFhVNdO"
FIGMA_PAGE_ID = "71:2"
FRAME_TAGS = {"frame", "component", "instance", "section", "group"}


def parse_sse(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8")
    for line in text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    if not text.strip():
        return {}
    return json.loads(text)


class MCPClient:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self.request_id = 0
        self.lock = threading.Lock()
        result, headers = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "codex-figma-snapshot",
                        "version": "1.0",
                    },
                },
            },
            include_session=False,
        )
        self.session_id = headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("Local Figma MCP did not return a session ID")
        if "error" in result:
            raise RuntimeError(result["error"])
        self._post(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
        tools, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            }
        )
        self.tool_names = {
            tool["name"] for tool in tools.get("result", {}).get("tools", [])
        }

    def _next_id(self) -> int:
        with self.lock:
            self.request_id += 1
            return self.request_id

    def _post(
        self,
        payload: dict[str, Any],
        *,
        include_session: bool = True,
        timeout: int = 120,
    ) -> tuple[dict[str, Any], Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if include_session and self.session_id:
            headers["mcp-session-id"] = self.session_id
        request = urllib.request.Request(
            MCP_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return parse_sse(body), response.headers

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.tool_names:
            raise RuntimeError(f"Local Figma MCP tool is unavailable: {name}")
        response, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if "error" in response:
            raise RuntimeError(response["error"])
        result = response.get("result", {})
        if result.get("isError"):
            text = "\n".join(
                item.get("text", "")
                for item in result.get("content", [])
                if item.get("type") == "text"
            )
            raise RuntimeError(text or f"Figma MCP tool failed: {name}")
        return result


def first_text(result: dict[str, Any]) -> str:
    for item in result.get("content", []):
        if item.get("type") == "text":
            return item["text"]
    raise RuntimeError("Figma MCP result contains no text")


def save_screenshot(result: dict[str, Any], path: Path) -> dict[str, Any]:
    for item in result.get("content", []):
        if item.get("type") == "image":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(item["data"]))
            return {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "mimeType": item.get("mimeType", "image/png"),
                "bytes": path.stat().st_size,
            }
    return {"path": None, "warning": "Local MCP returned no inline screenshot image"}


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sanitize(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "screen"
    if value[0].isdigit():
        value = f"n_{value}"
    return value


def next_version_directory(manifest_root: Path) -> tuple[int, Path, str]:
    versions = []
    for path in manifest_root.iterdir():
        if not path.is_dir():
            continue
        match = re.match(r"v(\d+)(?:_|$)", path.name)
        if match:
            versions.append(int(match.group(1)))
    version = max(versions, default=0) + 1
    date_token = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    directory = manifest_root / f"v{version}_all_{date_token}_context"
    snapshot = (
        f"{date_token[:4]}-{date_token[4:6]}-{date_token[6:]}-"
        f"v{version}-all-full-refresh"
    )
    return version, directory, snapshot


def manifest_version_from_directory(output_dir: Path, fallback: int) -> int:
    match = re.match(r"v(\d+)(?:_|$)", output_dir.name)
    return int(match.group(1)) if match else fallback


def root_relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def compact_row_to_source_row(row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("t") or {}
    return {
        "id": row["id"],
        "name": row.get("n", ""),
        "node_type": str(row.get("ty", "")).lower(),
        "parent_id": row.get("p"),
        "order": int(row.get("o", 0)),
        "path": row.get("path", ""),
        "x": float(row.get("x", 0)),
        "y": float(row.get("y", 0)),
        "width": float(row.get("w", 0)),
        "height": float(row.get("h", 0)),
        "fill": row.get("f"),
        "stroke": row.get("s"),
        "fill_paints": row.get("fp", []),
        "stroke_paints": row.get("sp", []),
        "stroke_width": float(row.get("sw", 0)),
        "corner_radius": float(row.get("r", 0)),
        "opacity": int(row.get("op", 255)),
        "visible": bool(row.get("v", True)),
        "clips_content": bool(row.get("clip", False)),
        "text": text.get("c"),
        "font_size": text.get("fs"),
        "font_family": text.get("ff"),
        "font_style": text.get("fy"),
        "text_align": text.get("a"),
        "line_height": text.get("lh"),
        "image_hash": row.get("img"),
        "image_reference": None,
    }


def load_remote_chunks(
    chunk_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    roots: dict[str, list[dict[str, Any]]] = {}
    capture_meta: dict[str, dict[str, Any]] = {}
    for directory in sorted(path for path in chunk_root.iterdir() if path.is_dir()):
        chunk_files = sorted(
            directory.glob("manifest_*.json"),
            key=lambda path: int(path.stem.rsplit("_", 1)[1]),
        )
        if not chunk_files:
            raise RuntimeError(f"No compact chunks found in {directory}")
        rows: list[dict[str, Any]] = []
        starts: list[int] = []
        total: int | None = None
        root_id: str | None = None
        for chunk_file in chunk_files:
            payload = json.loads(chunk_file.read_text(encoding="utf-8"))
            if payload.get("schema") != "figma-compact-manifest/v1":
                raise RuntimeError(f"Unsupported compact schema: {chunk_file}")
            current_root = str(payload["rootId"])
            current_total = int(payload["total"])
            if root_id is None:
                root_id = current_root
                total = current_total
            if current_root != root_id or current_total != total:
                raise RuntimeError(f"Inconsistent compact chunks in {directory}")
            starts.append(int(payload["start"]))
            rows.extend(payload.get("nodes", []))
        assert root_id is not None and total is not None
        expected_starts = list(range(0, total, 40))
        if starts != expected_starts:
            raise RuntimeError(
                f"Non-contiguous compact chunks for {root_id}: {starts}"
            )
        node_ids = [str(row["id"]) for row in rows]
        if len(rows) != total:
            raise RuntimeError(
                f"Compact node count mismatch for {root_id}: {len(rows)} != {total}"
            )
        if len(node_ids) != len(set(node_ids)):
            raise RuntimeError(f"Duplicate compact node IDs for {root_id}")
        if str(rows[0]["id"]) != root_id:
            raise RuntimeError(f"Compact root row missing for {root_id}")
        roots[root_id] = rows
        capture_meta[root_id] = {
            "chunk_count": len(chunk_files),
            "chunk_files": [root_relative_path(path) for path in chunk_files],
        }
    return roots, capture_meta


def snapshot_remote_chunks(
    *,
    source_index: dict[str, Any],
    output_dir: Path,
    chunk_root: Path,
    screenshot_dir: Path,
    snapshot_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    compact_roots, capture_meta = load_remote_chunks(chunk_root)
    previous = {str(row["id"]): row for row in source_index["roots"]}
    missing = sorted(set(previous) - set(compact_roots))
    if missing:
        raise RuntimeError(f"Remote capture is missing roots: {missing}")

    ordered_ids = [str(row["id"]) for row in source_index["roots"]]
    ordered_ids.extend(sorted(set(compact_roots) - set(ordered_ids)))
    roots: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    for order, root_id in enumerate(ordered_ids):
        rows = compact_roots[root_id]
        root_row = rows[0]
        old = previous.get(root_id)
        if old is None:
            target = sanitize(root_row.get("n", ""))
            if not target.lower().startswith("screen_"):
                target = f"screen_{target}"
            spec = {
                "id": root_id,
                "name": root_row.get("n", ""),
                "target_name": target,
                "kind": "screen",
                "directory": root_id.replace(":", "_"),
                "mapping_status": "new_root_requires_semantic_review",
            }
        else:
            spec = dict(old)
            spec["name"] = root_row.get("n", old["name"])

        screenshot_path = screenshot_dir / f"{root_id.replace(':', '_')}.png"
        if not screenshot_path.is_file():
            raise RuntimeError(f"Missing remote screenshot: {screenshot_path}")
        signature = screenshot_path.read_bytes()[:8]
        if signature != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"Invalid PNG screenshot: {screenshot_path}")

        root_dir = output_dir / spec["directory"]
        root_dir.mkdir(parents=True, exist_ok=True)
        compact_payload = {
            "schema": "figma-compact-manifest/v1",
            "rootId": root_id,
            "total": len(rows),
            "start": 0,
            "limit": len(rows),
            "nodes": rows,
        }
        (root_dir / "manifest.json").write_text(
            json.dumps(compact_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        source_tree = {
            "schema_version": "figma-source-node-tree/v1",
            "root_id": root_id,
            "node_count": len(rows),
            "nodes": [compact_row_to_source_row(row) for row in rows],
        }
        (root_dir / "source_tree.json").write_text(
            json.dumps(source_tree, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        spec["screenshot"] = root_relative_path(screenshot_path)
        spec["source_tree"] = f"{spec['directory']}/source_tree.json"
        spec["compact_manifest"] = f"{spec['directory']}/manifest.json"
        spec["node_count"] = len(rows)
        spec["capture"] = capture_meta[root_id]
        roots.append(spec)
        results.append(
            {
                "id": root_id,
                "name": spec["name"],
                "node_count": len(rows),
                "screenshot": {"path": spec["screenshot"]},
            }
        )
        inventory_rows.append(
            {
                "id": root_id,
                "name": spec["name"],
                "node_type": str(root_row.get("ty", "")).lower(),
                "order": order,
                "x": float(root_row.get("x", 0)),
                "y": float(root_row.get("y", 0)),
                "width": float(root_row.get("w", 0)),
                "height": float(root_row.get("h", 0)),
            }
        )

    inventory = {
        "page_id": FIGMA_PAGE_ID,
        "top_level_count": len(inventory_rows),
        "current": inventory_rows,
        "added": [
            row for row in inventory_rows if row["id"] not in previous
        ],
        "deleted": [
            row for row in source_index["roots"] if row["id"] not in compact_roots
        ],
        "renamed": [
            {
                "id": row["id"],
                "old_name": previous[row["id"]]["name"],
                "new_name": row["name"],
            }
            for row in inventory_rows
            if row["id"] in previous
            and row["name"] != previous[row["id"]]["name"]
        ],
        "capture_mode": "remote_mcp_compact_chunks",
        "snapshot": snapshot_version,
    }
    return roots, results, inventory


def discover_roots(
    client: MCPClient,
    source_index: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata = first_text(
        client.call(
            "get_metadata",
            {
                "nodeId": FIGMA_PAGE_ID,
                "clientFrameworks": "unknown",
                "clientLanguages": "json,python",
            },
        )
    )
    canvas = ET.fromstring(metadata)
    current = []
    for order, child in enumerate(list(canvas)):
        if child.tag.lower() not in FRAME_TAGS:
            continue
        current.append(
            {
                "id": child.attrib["id"],
                "name": child.attrib.get("name", ""),
                "node_type": child.tag.lower(),
                "order": order,
                "x": float(child.attrib.get("x", 0)),
                "y": float(child.attrib.get("y", 0)),
                "width": float(child.attrib.get("width", 0)),
                "height": float(child.attrib.get("height", 0)),
            }
        )

    previous = {row["id"]: row for row in source_index["roots"]}
    current_by_id = {row["id"]: row for row in current}
    roots: list[dict[str, Any]] = []
    for old in source_index["roots"]:
        live = current_by_id.get(old["id"])
        if live is None:
            continue
        row = dict(old)
        row["name"] = live["name"]
        roots.append(row)
    known_ids = {row["id"] for row in roots}
    for live in current:
        if live["id"] in known_ids:
            continue
        target = sanitize(live["name"])
        if not target.lower().startswith("screen_"):
            target = f"screen_{target}"
        roots.append(
            {
                "id": live["id"],
                "name": live["name"],
                "target_name": target,
                "kind": "screen",
                "directory": live["id"].replace(":", "_"),
                "screenshot": None,
                "mapping_status": "new_root_requires_semantic_review",
            }
        )

    inventory = {
        "page_id": FIGMA_PAGE_ID,
        "top_level_count": len(current),
        "current": current,
        "added_root_ids": [
            row["id"] for row in current if row["id"] not in previous
        ],
        "removed_root_ids": [
            row["id"] for row in source_index["roots"] if row["id"] not in current_by_id
        ],
        "renamed_roots": [
            {
                "id": row["id"],
                "old_name": previous[row["id"]]["name"],
                "new_name": row["name"],
            }
            for row in current
            if row["id"] in previous and row["name"] != previous[row["id"]]["name"]
        ],
    }
    return roots, inventory


def serialize_source_tree(raw_path: Path, output_path: Path) -> int:
    import sync_completed_figma_to_guiguider as sync

    _, metadata, tsx, _ = sync.extract_sections(raw_path.read_text(encoding="utf-8"))
    root = sync.parse_source_tree(metadata, tsx)
    rows: list[dict[str, Any]] = []

    def visit(node: sync.SourceNode, path: str, order: int) -> None:
        rows.append(
            {
                "id": node.id,
                "name": node.name,
                "node_type": node.tag,
                "parent_id": node.parent.id if node.parent else None,
                "order": order,
                "path": path,
                "x": node.x,
                "y": node.y,
                "width": node.width,
                "height": node.height,
                "fill": list(node.fill) if node.fill else None,
                "stroke": list(node.stroke) if node.stroke else None,
                "stroke_width": node.stroke_width,
                "corner_radius": node.corner_radius,
                "opacity": node.opacity,
                "visible": not node.hidden,
                "clips_content": node.clips_content,
                "text": node.text,
                "font_size": node.font_size,
                "font_family": node.font_family,
                "font_style": node.font_style,
                "text_align": node.text_align,
                "line_height": node.line_height,
                "image_hash": node.image_hash,
                "image_reference": node.asset_url,
            }
        )
        for child_order, child in enumerate(node.children):
            visit(child, f"{path}/{child.name or child.id}", child_order)

    visit(root, root.name or root.id, 0)
    payload = {
        "schema_version": "figma-source-node-tree/v1",
        "root_id": root.id,
        "node_count": len(rows),
        "nodes": rows,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return len(rows)


def snapshot_one(
    spec: dict[str, Any],
    output_dir: Path,
    screenshot_dir: Path,
    *,
    snapshot_version: str,
    skip_screenshot: bool,
) -> dict[str, Any]:
    client = MCPClient()
    context = client.call(
        "get_design_context",
        {
            "nodeId": spec["id"],
            "clientFrameworks": "unknown",
            "clientLanguages": "json,python",
            "artifactType": "WEB_PAGE_OR_APP_SCREEN",
            "taskType": "CHANGE_ARTIFACT",
        },
    )
    metadata = client.call(
        "get_metadata",
        {
            "nodeId": spec["id"],
            "clientFrameworks": "unknown",
            "clientLanguages": "json,python",
        },
    )
    if skip_screenshot:
        screenshot_info = {
            "path": str(
                (
                    screenshot_dir / f"{spec['id'].replace(':', '_')}.png"
                ).relative_to(ROOT)
            ).replace("\\", "/"),
            "pending_remote_mcp_capture": True,
        }
    else:
        screenshot = client.call(
            "get_screenshot",
            {"nodeId": spec["id"], "contentsOnly": True},
        )
        screenshot_info = save_screenshot(
            screenshot,
            screenshot_dir / f"{spec['id'].replace(':', '_')}.png",
        )
    source = {
        "file_key": FIGMA_FILE_KEY,
        "page_id": FIGMA_PAGE_ID,
        "root_id": spec["id"],
        "root_name": spec["name"],
        "target_name": spec["target_name"],
        "kind": spec["kind"],
        "tools": [
            "figma_local.get_design_context",
            "figma_local.get_metadata",
            "figma_local.get_screenshot",
        ],
        "read_only": True,
        "snapshot": snapshot_version,
    }
    raw = (
        "=== SOURCE ===\n"
        + json.dumps(source, ensure_ascii=False, indent=2)
        + "\n=== METADATA_XML ===\n"
        + first_text(metadata)
        + "\n=== DESIGN_CONTEXT_TSX ===\n"
        + first_text(context)
        + "\n=== SCREENSHOT_JSON ===\n"
        + json.dumps(screenshot_info, ensure_ascii=False, indent=2)
        + "\n"
    )
    root_dir = output_dir / spec["directory"]
    root_dir.mkdir(parents=True, exist_ok=True)
    raw_path = root_dir / "raw_context.txt"
    raw_path.write_text(raw, encoding="utf-8", newline="\n")
    node_count = serialize_source_tree(raw_path, root_dir / "source_tree.json")
    return {
        "id": spec["id"],
        "name": spec["name"],
        "raw_bytes": len(raw.encode("utf-8")),
        "node_count": node_count,
        "screenshot": screenshot_info,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-index", type=Path, default=DEFAULT_SOURCE_INDEX)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--snapshot-version")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--remote-chunks",
        type=Path,
        help="Use an already captured remote compact-manifest chunk directory.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        help="Screenshot directory used with --remote-chunks.",
    )
    parser.add_argument(
        "--skip-screenshot",
        action="store_true",
        help="Capture screenshots separately through the remote Figma MCP.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_index = json.loads(args.source_index.read_text(encoding="utf-8"))
    expected_parent = (ROOT / "manifests").resolve()
    auto_version, auto_output, auto_snapshot = next_version_directory(expected_parent)
    output_dir = (args.output_dir or auto_output).resolve()
    manifest_version = manifest_version_from_directory(output_dir, auto_version)
    snapshot_version = args.snapshot_version or auto_snapshot
    if expected_parent not in output_dir.parents:
        raise RuntimeError(f"Output directory must stay under {expected_parent}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite non-empty Manifest: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = (
        args.screenshot_dir
        or ROOT / "artifacts" / f"figma_reference_{output_dir.name}"
    ).resolve()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    if args.remote_chunks:
        if not args.screenshot_dir:
            raise RuntimeError("--remote-chunks requires --screenshot-dir")
        refreshed_roots, results, inventory = snapshot_remote_chunks(
            source_index=source_index,
            output_dir=output_dir,
            chunk_root=args.remote_chunks.resolve(),
            screenshot_dir=screenshot_dir,
            snapshot_version=snapshot_version,
        )
    else:
        discovery_client = MCPClient()
        roots, inventory = discover_roots(discovery_client, source_index)
        results = []
        errors: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(
                    snapshot_one,
                    spec,
                    output_dir,
                    screenshot_dir,
                    snapshot_version=snapshot_version,
                    skip_screenshot=args.skip_screenshot,
                ): spec
                for spec in roots
            }
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(
                        f"OK {result['id']} {result['name']} "
                        f"raw={result['raw_bytes']} bytes"
                    )
                except Exception as error:  # noqa: BLE001 - aggregate all roots.
                    errors.append({"id": spec["id"], "error": str(error)})
                    print(f"ERROR {spec['id']} {error}")
        if errors:
            raise RuntimeError(json.dumps(errors, ensure_ascii=False, indent=2))
        by_id = {result["id"]: result for result in results}
        refreshed_roots = []
        for spec in roots:
            item = dict(spec)
            item["screenshot"] = by_id[spec["id"]]["screenshot"]["path"]
            item["source_tree"] = f"{spec['directory']}/source_tree.json"
            item["node_count"] = by_id[spec["id"]]["node_count"]
            refreshed_roots.append(item)
    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    index = {
        "schema_version": "figma-local-raw-context-index/v2",
        "manifest_version": manifest_version,
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "base_manifest": str(args.source_index.resolve()),
        "checksums_file": "checksums.json",
        "source": {
            "file_key": FIGMA_FILE_KEY,
            "page_id": FIGMA_PAGE_ID,
            "tools": (
                [
                    "figma_remote.use_figma",
                    "figma_remote.get_screenshot",
                ]
                if args.remote_chunks
                else [
                    "figma_local.get_design_context",
                    "figma_local.get_metadata",
                    "figma_local.get_screenshot",
                ]
            ),
            "read_only": True,
            "capture_mode": (
                "remote_mcp_compact_chunks"
                if args.remote_chunks
                else "local_mcp_design_context"
            ),
        },
        "root_inventory": inventory,
        "roots": refreshed_roots,
    }
    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    parsed_index = json.loads(index_path.read_text(encoding="utf-8"))
    if len(parsed_index["roots"]) != len(results):
        raise RuntimeError("Manifest index parse check failed")
    checksums: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            checksums[str(path.relative_to(ROOT)).replace("\\", "/")] = file_sha256(path)
    for spec in refreshed_roots:
        screenshot_path = ROOT / spec["screenshot"]
        if screenshot_path.is_file():
            checksums[str(screenshot_path.relative_to(ROOT)).replace("\\", "/")] = (
                file_sha256(screenshot_path)
            )
    checksum_payload = {
        "schema_version": "figma-manifest-checksums/v1",
        "manifest_version": manifest_version,
        "snapshot_version": snapshot_version,
        "generated_at": generated_at,
        "files": checksums,
    }
    (output_dir / "checksums.json").write_text(
        json.dumps(checksum_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"SNAPSHOT_COUNT={len(results)}")
    print(f"MANIFEST_VERSION={manifest_version}")
    print(f"INDEX={index_path}")
    print(f"CHECKSUMS={output_dir / 'checksums.json'}")


if __name__ == "__main__":
    main()
