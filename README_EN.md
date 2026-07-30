# Figma → GUI Guider 2.0 → LVGL 9.4

English | [简体中文](README.md)

[![Validate](https://github.com/houhouoch/Figma--GuiGuider2.0_V9.4-/actions/workflows/validate.yml/badge.svg)](https://github.com/houhouoch/Figma--GuiGuider2.0_V9.4-/actions/workflows/validate.yml)

This repository captures a production-tested, controlled workflow for converting **Figma designs into NXP GUI Guider 2.0 / LVGL 9.4 projects**. It includes the reviewed GUI Guider source project, versioned manifests, conversion and audit tools, engineering retrospectives, Obsidian-ready atomic notes, and an installable Codex Skill.

> The repository is scoped to Figma → GUI Guider. It does not contain or modify an MDK firmware project.

![GUI Guider preview](docs/preview.png)

## Verified scope

- Canvas: `960 × 240`
- Figma design roots: 31
- GUI Guider project entries: 34, including system layers
- V9 manifest nodes: 1,756
- Audited text labels: 664
- Project image assets: 50
- Target: GUI Guider 2.0, LVGL 9.4, RGB565

Key documents:

- [End-to-end engineering retrospective](docs/2026-07-30_FIGMA_TO_GUI_GUIDER_FULL_RETROSPECTIVE.md)
- [Duplicate project ID opens the old project](docs/2026-07-30_GUI_GUIDER_DUPLICATE_PROJECT_ID_BUG_EN.md)
- [Font and Label retrospective](docs/2026-07-29_GUI_GUIDER_FONT_AND_LABEL_RETROSPECTIVE.md)
- [Figma → GUI Guider 2.0 / LVGL 9.4 guide](docs/FIGMA_TO_GUI_GUIDER_2_0_LVGL_9_4_GUIDE.md)
- [Workflow and pitfalls](docs/FIGMA_TO_LVGL_WORKFLOW_AND_PITFALLS.md)

## Repository layout

```text
project/                  GUI Guider template project and project images
manifests/                Versioned structured Figma snapshots
tools/                    Conversion, comparison, audit and promotion tools
skills/                   Installable Codex Skill
docs/                     Guides, retrospectives and validation evidence
knowledge-export/obsidian Obsidian-ready atomic notes
.github/                  CI, issue and pull-request conventions
```

The repository intentionally excludes:

- NXP GUI Guider installers, `platform/`, and simulator toolchains;
- MDK projects;
- GUI Guider generated C sources;
- third-party font binaries.

## Quick start

### 1. Clone

```bash
git clone https://github.com/houhouoch/Figma--GuiGuider2.0_V9.4-.git
cd Figma--GuiGuider2.0_V9.4-
```

### 2. Install external dependencies

1. Install GUI Guider 2.0 from the [official NXP page](https://www.nxp.com/design/software/development-software/gui-guider:GUI-GUIDER) and accept its license.
2. Download Alibaba PuHuiTi 2.0 Regular TTF from the [official Alibaba Design page](https://done.alibabadesign.com/puhuiti2.0).

The font is not redistributed in this repository. Its required project basename is:

```text
AlibabaPuHuiTi2.ttf
```

### 3. Prepare a local project

Windows example:

```powershell
python tools/prepare_local_project.py `
  --font "D:\path\to\AlibabaPuHuiTi2.ttf"
```

The script copies the font, replaces the machine-specific `projectPath`,
assigns a clone-specific `projectId` and project name, and creates:

```text
project/guiguider_2.0.guiguider
```

Open that file in GUI Guider 2.0. Do not open the template directly.

By default, the script refuses to overwrite an existing local project so that
manual GUI Guider edits cannot be reset accidentally. Use `--force` only when
an intentional rebuild from the template is required.

Rebuilding project images with the historical conversion scripts additionally
requires an authorized source-asset pack under `external-assets/source/`, or
the `FIGMA_GUI_GUIDER_ASSET_ROOT` environment variable. It is not required to
open and review the published GUI Guider project.

### 4. Validate

```bash
python tools/validate_repository.py
python skills/figma-to-guiguider-controlled-sync/scripts/audit_guiguider_project.py \
  --project project/guiguider_2.0.guiguider
```

Run the second command after local project preparation.

### 5. Generate LVGL code

Click **Generate Code** in GUI Guider. Generated output is intentionally ignored. Before accepting it, compare custom-font references, declarations, and definitions, then perform a clean simulator build.

## Install the Codex Skill

With the Skills CLI:

```bash
npx skills add https://github.com/houhouoch/Figma--GuiGuider2.0_V9.4-.git \
  --skill figma-to-guiguider-controlled-sync
```

Or copy `skills/figma-to-guiguider-controlled-sync` to:

```text
%USERPROFILE%\.codex\skills\figma-to-guiguider-controlled-sync
```

Example prompt:

```text
Use $figma-to-guiguider-controlled-sync.
Synchronize only the selected Figma screen into an isolated GUI Guider 2.0
candidate while preserving stable object IDs, events, variables, fonts,
and non-UI project configuration.
```

## Controlled synchronization

```text
Complete Figma snapshot
  → versioned manifest
  → semantic diff and field-ownership audit
  → isolated candidate
  → resource-closure and typography audit
  → visual comparison
  → explicit user approval
  → backup and formal promotion
  → GUI Guider open/save/close round trip
  → Generate Code + simulator build
```

Never treat a partial or rate-limited capture as a valid manifest, and never write a newly converted tree directly into the formal `.guiguider` project.

## Licensing and third-party content

Original automation scripts and the Codex Skill are available under the MIT License. UI designs, images, third-party fonts, NXP GUI Guider, and LVGL remain subject to their respective rights and licenses. See [THIRD_PARTY_NOTICES_EN.md](THIRD_PARTY_NOTICES_EN.md).

## Contributing

Read [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md). Converter changes must include a fixed input manifest, deterministic candidate output, idempotency evidence, structural/resource/typography/visual checks, and an explicit formal-project protection boundary.
