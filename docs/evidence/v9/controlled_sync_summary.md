# V9 Controlled Sync Summary

## Result

- Candidate is ready for human review: **yes**
- Candidate is eligible for formal promotion: **no**
- Formal GUI Guider project changed: **no**
- MDK project changed: **no**
- GUI Guider open/save roundtrip verified: **no**

The run intentionally stops at the candidate stage. Promotion remains blocked
until GUI Guider 2.0 opens/saves the candidate successfully and the listed
manual controls are reviewed.

## Outputs

- Manifest: `D:\figma\V2.0\guiguider_2.0\guiguider_2.0\tools\manifests\v9_all_20260729_context\index.json`
- Manifest version: `2026-07-29-v9-all-full-refresh`
- Candidate: `D:\figma\V2.0\guiguider_2.0\guiguider_2.0\tools\artifacts\figma_sync_20260729_v9_controlled\guiguider_2.0.v9_candidate.guiguider`
- Candidate SHA-256: `9e297c7cc62d302fbf307471e28826fd5cdc6bf4ba893d20980a149c7816fd51`
- Report directory: `D:\figma\V2.0\guiguider_2.0\guiguider_2.0\tools\sync_reports\v9_all_20260729_context`

## Change Summary

- Pages: 31 -> 31
- Nodes: 1615 -> 1756
- Automatically matched nodes: 1615
- Identity-uncertain nodes: 0
- Added nodes: 141
- Renamed nodes: 25
- Parent changes: 388
- Type/semantic changes: 1
- Potential business-impact changes: 414

## Validation

- Structural blocking issues: 0
- Minimum whole-page similarity: 0.944107
- Previous baseline: 0.940617
- Baseline delta: +0.003490
- Minimum regional similarity: 0.680751
- Regional failures: 0
- Image widgets / unique resources: 112 / 49
- Idempotent output: True
- V8 converter regression passed: True

## Manual Review

- **Home**: img_status_beep_no, six changed text/font metrics, voltage/current/unit regions. Only control type change: container to image; also the lowest whole-page score.
- **Menu_Admin, Menu_Digital_IO, screen_List, Menu_Date, Menu_Log**: reparented and newly added controls. Highest parent-tree churn.
- **Menu_Protect, Menu_Coupling, Menu_Info, screen_Arb, Menu_Communication**: reparented and newly added controls. Material parent-tree and geometry changes.
- **screen_recall, screen_save**: slot index labels. Confirm 24 existing manual icon-label coordinate corrections remain intentional.
- **screen_mode_select_large, screen_mode_select_small**: overlay roots 365:2 and 365:5. Imported as standalone preview screens; runtime overlay semantics remain manual.
- **Scrollable pages and containers**: screen_coupling, screen_measure, screen_protect, screen_config, screen_digital_io, screen_admin, screen_communication, cont_menu_function, cont_info_list_cont. Confirm physical-key focus navigation, clipping, and hidden scrollbars in GUI Guider.
