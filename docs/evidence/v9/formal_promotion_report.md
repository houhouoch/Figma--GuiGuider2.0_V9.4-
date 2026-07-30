# V9 Formal GUI Guider Promotion

## Result

- User approval recorded: **yes**
- Candidate promoted to the formal project: **yes**
- Non-UI project configuration preserved: **yes**
- Formal UI matches the validated candidate: **yes**
- Required image and font resources present: **50 / 50**
- GUI Guider 2.0 open/save/close roundtrip: **pass**
- MDK project changed: **no**

## Font Correction

The first isolated review workspace copied image resources but did not register
the custom font in GUI Guider. This caused fallback-font rendering, including
missing glyphs, incorrect sizes, shifted baselines, and clipping.

The accepted project uses `resources/font/AlibabaPuHuiTi2.0.ttf`. The complete
typography audit confirms:

- 664 Figma text nodes mapped.
- 647 existing GUI labels matched.
- 17 new labels added.
- 0 matched font-family changes.
- 0 matched font-size changes.
- 0 Figma-to-GUI font-family mismatches.
- 0 Figma-to-GUI font-size mismatches.

## Integrity

- Pre-promotion formal SHA-256:
  `4c85aabad353f61fa35281416f613330ff3380fd3835e324026434c8528aff0b`
- Validated candidate SHA-256:
  `9e297c7cc62d302fbf307471e28826fd5cdc6bf4ba893d20980a149c7816fd51`
- Formal SHA-256 before GUI Guider save:
  `bc7ec48eefaffc9277f5602d88768edba944c5a209934296d9fc11cb37b4ec00`
- Formal SHA-256 after GUI Guider save:
  `5b07a55d945188dbe08bdf2a7fe3169e3cde473d2469a66595020095e3b87ab0`

GUI Guider changed only `lastModified` during the final save. The UI tree and
resource references remained byte-equivalent at the JSON value level.
