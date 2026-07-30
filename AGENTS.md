# GUI Guider Project Rules

## Scope Boundaries

- When a task explicitly asks to modify only the GUI Guider project, do not
  rerun the Figma converter and do not modify MDK.
- Treat `guiguider_2.0.guiguider` as the source of truth for direct GUI Guider
  fixes. Close GUI Guider before editing it, preserve object IDs/names/business
  fields, and validate the JSON after editing.
- Distinguish full Figma synchronization, one-screen synchronization, and a
  direct GUI Guider fix before changing files. A one-screen or direct fix must
  not rewrite unrelated screens.

## Controlled Figma Synchronization

- Never write a newly converted Figma tree directly into the formal
  `guiguider_2.0.guiguider`. Generate an independent candidate first.
- Treat a Figma snapshot as valid only after all expected roots and chunks have
  been received and node totals, chunk continuity, unique Figma IDs, and file
  checksums pass. A partial or rate-limited snapshot is not a manifest.
- Preserve the formal project's identity and non-UI configuration. Figma may
  update reviewed visual hierarchy, geometry, and style fields; it must not
  silently replace stable GUI Guider object IDs/names, events, variables,
  focus bindings, callbacks, dynamic values, or project/LVGL configuration.
- Block and report control-type changes, missing/deleted mapped objects, and
  changes that may affect events, focus, or business code.
- Require deterministic candidate generation, schema/resource validation,
  regression comparison, and visual review before asking for promotion.

## Review And Promotion

- An isolated GUI Guider review workspace must use a distinct project ID,
  project name, project path, and resource directory. A different `.guiguider`
  filename alone is not sufficient isolation.
- A cloned or prepared local project must also receive a clone-specific
  `projectId`. GUI Guider 2.0 can associate duplicate IDs with the old recent
  project path, making edits appear locked or unsaved.
- When GUI Guider restores the wrong project, verify the visible project name,
  internal `projectId/projectPath`, and
  `%APPDATA%\GUIGuider\2.0.0\project_history.json`. Process startup alone does
  not prove that the intended project is loaded.
- Local preparation tools must refuse to overwrite an existing editable
  project unless replacement is explicitly requested.
- Copy the complete resource closure for review, including fonts referenced
  only by `text_family` as well as images with explicit paths. Missing or
  unregistered fonts invalidate size, baseline, clipping, and position review.
- Promote a candidate only after explicit user approval. Create and verify a
  backup, preserve non-UI configuration, update only the approved UI tree, and
  verify every referenced image and font.
- Complete a GUI Guider open/save/close roundtrip after promotion. Compare the
  saved JSON and allow only documented volatile metadata such as
  `lastModified`; any UI or configuration rewrite must be investigated.
- GUI Guider open/save success is not the final code-generation check. Generate
  C and run a full simulator build before accepting the result.

## Custom Fonts

- Custom font resource basenames must be C-identifier-safe: use letters,
  numbers, and underscores only. Do not use extra dots before `.ttf`.
- The `text_family` value in the `.guiguider` project must exactly match the
  filename under `resources/font`.
- Before accepting generated code, compare these three symbol sets:
  1. font references in `generated/screens/*.c`;
  2. declarations in `generated/assets/fonts/gg_font.h`;
  3. definitions in `generated/assets/fonts/lv_font_*.c`.
- All three symbol sets must match, and a full simulator build must succeed.

## Label Geometry

- Do not assume Figma text bounds or TTF ascent/descent are valid GUI Guider
  Label heights.
- After a Figma import, audit single-line Label heights grouped by font size,
  then obtain visual confirmation before promoting a new height rule.
- Do not generalize the current project's `font size + 5 px` observation to
  another font or GUI Guider version until it has been visually verified there.
