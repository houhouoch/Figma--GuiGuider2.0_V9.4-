# Promotion Gates And Field Ownership

## Contents

1. Snapshot gate
2. Conversion gate
3. Review workspace gate
4. Promotion gate
5. Code-generation gate
6. Field ownership

## 1. Snapshot Gate

Require:

- expected root count;
- complete chunk ranges;
- reported total equals merged node count;
- unique Figma IDs;
- screenshots and source files have checksums;
- final completion marker written only after all checks pass.

Never accept a half-created version directory as a manifest.

## 2. Conversion Gate

Require:

- stable existing GUI Guider IDs/names preserved;
- business-owned fields preserved;
- type changes and deleted mapped objects listed as blockers;
- images content-deduplicated;
- repeated conversion produces the same semantic output;
- old-version regression contracts remain unchanged.

## 3. Review Workspace Gate

Require:

- distinct `projectId`, `projectName`, and `projectPath`;
- independent resource directory;
- every referenced image present;
- every `text_family` font present and registered;
- GUI Guider visibly loads the intended project, not only the process path;
- high-churn screens reviewed manually.

Missing fonts invalidate typography and geometry review.

## 4. Promotion Gate

Require:

- explicit user approval;
- verified backup of the formal `.guiguider`;
- formal non-UI configuration preserved;
- approved candidate UI copied;
- all resources resolved;
- open/save/close roundtrip completed;
- saved JSON differs only in documented volatile metadata.

## 5. Code-Generation Gate

Require:

- custom font references, declarations, and definitions form equal sets;
- a clean simulator build succeeds;
- representative pages are visually checked for fallback fonts, clipping, baselines, scroll, overlays, and focus behavior.

## 6. Field Ownership

| Data | Owner | Rule |
|---|---|---|
| Figma node identity | Mapping layer | Use stable Figma ID; never guess identity silently |
| Visual parent/order/geometry/style | Figma after review | Update in candidate |
| GUI Guider object ID/name | GUI Guider | Preserve existing values |
| Project identity/settings/LVGL config | Formal GUI Guider project | Preserve |
| Events/variables/focus/callbacks | Business layer | Preserve and validate |
| Dynamic values | Runtime/business layer | Do not overwrite with Figma sample text |
| Images | Resource layer | Prefer reviewed transparent originals and content hashes |
| Fonts | Resource + typography layer | Copy/register complete font closure |
