# Formal Promotion Gate

- Candidate review readiness: **True**
- Formal promotion allowed: **False**

## Conditions

- `PASS` formal_project_hash_guard: Formal .guiguider SHA-256 matches the task-start value.
- `PASS` automatic_structure_and_visual_validation: No structural blockers or failed critical visual regions.
- `PASS` deterministic_generation: Two candidate generations have identical SHA-256.
- `PASS` v8_converter_regression: V8 object, resource, event, and configuration contracts remain stable.
- `BLOCKED` type_change_manual_review: Home/img_status_beep_no container-to-image change requires review.
- `BLOCKED` gui_guider_open_save_roundtrip: Automation was interrupted before a verified open/save/close roundtrip.
- `BLOCKED` manual_page_review: High-churn pages, scroll behavior, overlays, and Recall/Save must be inspected.
- `BLOCKED` explicit_promotion_approval: This run is required to stop at the candidate stage.
