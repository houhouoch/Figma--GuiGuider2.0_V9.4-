---
name: figma-to-guiguider-controlled-sync
description: Safely convert or synchronize Figma screens into GUI Guider 2.0 projects through versioned manifests, field-ownership rules, isolated candidates, complete image/font resource closure, visual and schema validation, explicit promotion approval, and generated-font contract checks. Use for full Figma-to-GUI-Guider imports, one-screen/node updates, candidate review, formal .guiguider promotion, missing-font or wrong-project review failures, and GUI Guider generated C font-symbol errors.
---

# Figma To GUI Guider Controlled Sync

## Choose The Operation

Classify the request before editing:

- **Full sync**: capture every expected Figma root and build a new candidate.
- **One-screen sync**: capture only the named root/subtree and prove all other screens are unchanged.
- **Direct GUI Guider fix**: edit the formal `.guiguider` only after closing GUI Guider; do not rerun Figma conversion.

Do not modify MDK unless the user separately requests firmware integration.

## Execute The Controlled Workflow

1. Inspect Git status and preserve unrelated edits.
2. Record the formal `.guiguider` SHA-256 and create a recoverable baseline.
3. Capture Figma into a versioned manifest:
   - chunk large roots;
   - verify expected roots, chunk continuity, node totals, unique Figma IDs, screenshots, and checksums;
   - reject partial or rate-limited output.
4. Compare old and new manifests. Classify additions, deletions, renames, reparenting, geometry, style, resources, and type changes.
5. Apply field ownership:
   - Figma owns reviewed visual hierarchy, geometry, and styles;
   - GUI Guider owns project identity/configuration and stable object IDs/names;
   - business code owns events, variables, focus, callbacks, and dynamic state.
6. Generate an independent candidate. Never overwrite the formal project at this stage.
7. Generate the candidate twice and require identical semantic output.
8. Create an isolated review workspace with a distinct project ID, name, path, and resource directory.
   - Apply the same identity isolation to editable local clones.
   - GUI Guider 2.0 may associate duplicate `projectId` values with the old
     recent-project path, making edits appear locked or unsaved.
   - Verify the visible project name and project history; a launched process
     does not prove that the intended project was loaded.
9. Copy the complete resource closure:
   - explicit image paths;
   - fonts referenced only by `text_family`;
   - verify files exist and are registered in GUI Guider.
10. Run schema, identity, resource, visual, regression, and generated-code audits.
11. Require manual review for type changes, high-churn parents, scrollable pages, overlays, and runtime-bound controls.
12. Promote only after explicit user approval:
   - create and verify a backup;
   - preserve non-UI configuration;
   - update only the approved UI tree;
   - verify resources again.
13. Open, save, and close the formal project in GUI Guider. Compare JSON and allow only documented volatile metadata such as `lastModified`.
14. Generate C and run a clean simulator build. GUI Guider opening successfully is not sufficient.

Read [references/gates.md](references/gates.md) when defining the promotion gate or diagnosing a failed stage.

## Enforce Typography And Resource Contracts

- Use C-identifier-safe custom font basenames: letters, digits, and underscores only.
- Require `.guiguider` `text_family` to match the file under `resources/font`.
- Compare generated font symbols across:
  - references in `generated/screens/*.c`;
  - declarations in `generated/assets/fonts/gg_font.h`;
  - definitions in `generated/assets/fonts/lv_font_*.c`.
- Treat missing fonts as a blocking review failure. Do not compensate fallback-font geometry by moving labels.
- Keep image alpha. Prefer reviewed transparent source assets over rasterized Figma frames that bake in backgrounds.
- Do not generalize a Label height formula across fonts or GUI Guider versions without visual verification.

Run the read-only audit:

```powershell
python scripts/audit_guiguider_project.py `
  --project D:\path\project.guiguider `
  --generated-dir D:\path\generated
```

## Stop Conditions

Stop before promotion when any of these occur:

- incomplete/rate-limited manifest;
- duplicate or missing stable IDs;
- unreviewed control-type change;
- missing image or font;
- candidate still uses the formal project identity;
- editable clone reuses another project's `projectId`;
- local preparation would overwrite an existing edited project without
  explicit replacement authorization;
- non-deterministic candidate output;
- regression or critical visual failure;
- missing explicit promotion approval;
- GUI Guider roundtrip rewrites UI/configuration;
- generated font references, declarations, and definitions differ.

Mark unverified hardware behavior, widget interaction, and cross-font geometry rules as `待确认`. Do not place them in general rules.
