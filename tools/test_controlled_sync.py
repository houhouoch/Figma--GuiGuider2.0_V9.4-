#!/usr/bin/env python3
"""Focused regression tests for the controlled Figma sync helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import prepare_local_project as local_project
import sync_completed_figma_to_guiguider as sync


class ControlledSyncTests(unittest.TestCase):
    def test_local_project_identity_is_clone_specific(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory:
            with tempfile.TemporaryDirectory() as second_directory:
                first = Path(first_directory) / "project.guiguider"
                second = Path(second_directory) / "project.guiguider"
                first_id = local_project.local_project_id(
                    local_project.DEFAULT_PROJECT_NAME,
                    first,
                )
                second_id = local_project.local_project_id(
                    local_project.DEFAULT_PROJECT_NAME,
                    second,
                )

        self.assertTrue(first_id.startswith("project-"))
        self.assertNotEqual(first_id, second_id)
        self.assertNotEqual(first_id, "project-MRWWUBKD5NV0")

    def test_compact_manifest_builds_parent_tree(self) -> None:
        payload = {
            "schema": "figma-compact-manifest/v1",
            "rootId": "1:1",
            "total": 2,
            "start": 0,
            "limit": 2,
            "nodes": [
                {
                    "id": "1:1",
                    "n": "Home",
                    "ty": "FRAME",
                    "p": None,
                    "o": 0,
                    "w": 960,
                    "h": 240,
                },
                {
                    "id": "1:2",
                    "n": "label_value",
                    "ty": "TEXT",
                    "p": "1:1",
                    "o": 0,
                    "x": 10,
                    "y": 20,
                    "w": 100,
                    "h": 30,
                    "t": {"c": "12.3", "fs": 24},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "manifest.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            root = sync.parse_compact_tree(path, {})
        self.assertEqual(root.id, "1:1")
        self.assertEqual([child.id for child in root.children], ["1:2"])
        self.assertIs(root.children[0].parent, root)

    def test_name_allocator_preserves_existing_owner(self) -> None:
        allocator = sync.NameAllocator(set(), {"label_value": "1:2"})
        self.assertNotEqual(allocator.allocate("label_value", "9:9"), "label_value")
        self.assertEqual(allocator.allocate("label_value", "1:2"), "label_value")

    def test_object_contract_keeps_identity_and_business_fields(self) -> None:
        rebuilt = {
            "id": "new-id",
            "figma_id": "1:2",
            "name": "new_name",
            "type": "label",
            "text": "new",
            "style": {"visual": True},
            "children": [],
        }
        existing = {
            "1:2": {
                "id": "stable-id",
                "figma_id": "1:2",
                "name": "stable_name",
                "type": "label",
                "text": "old",
                "style": {"visual": False},
                "children": [],
                "business_callback": "on_value_changed",
            }
        }
        report = {"preserved_object_contracts": []}
        sync.preserve_existing_object_contract(rebuilt, existing, report)
        self.assertEqual(rebuilt["id"], "stable-id")
        self.assertEqual(rebuilt["name"], "stable_name")
        self.assertEqual(rebuilt["text"], "new")
        self.assertEqual(rebuilt["style"], {"visual": True})
        self.assertEqual(rebuilt["business_callback"], "on_value_changed")

    def test_beep_off_uses_reviewed_transparent_asset(self) -> None:
        source = sync.LOCAL_ASSET_ROOT / sync.LOCAL_ASSET_BY_NODE_NAME[
            "img_status_beep_no"
        ]
        if not source.is_file():
            self.skipTest(
                "authorized external source-asset pack is not installed"
            )
        self.assertTrue(source.is_file())
        _, _, alpha = sync.png_has_alpha(source)
        self.assertTrue(alpha)


if __name__ == "__main__":
    unittest.main()
