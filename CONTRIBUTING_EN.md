# Contributing

English | [简体中文](CONTRIBUTING.md)

## Scope

- Never overwrite the formal GUI Guider project with a fresh conversion.
- Do not commit NXP GUI Guider files, `platform/`, build caches, or third-party fonts.
- A single-screen task may change only that screen and required shared declarations.
- A direct GUI Guider fix must not silently trigger a full Figma reconversion.

## Workflow

1. Start from a fixed manifest and a verified formal-project backup.
2. Generate an isolated candidate.
3. Compare object IDs, names, types, events, variables, fonts, and non-UI configuration.
4. Validate resource closure and font reference/declaration/definition contracts.
5. Generate twice and compare hashes for idempotency.
6. Perform visual review.
7. Promote only after explicit user approval.
8. Complete a GUI Guider open/save/close round trip.
9. Generate code and run a clean simulator build.

## Commits

Use focused English Conventional Commits:

```text
fix: preserve GUI Guider font symbols
docs: document controlled promotion workflow
```

Pull requests must identify the input manifest, affected screens, verification evidence, and any unperformed hardware or manual review.

## Validation

```bash
python tools/validate_repository.py
```

After preparing the external font:

```bash
python skills/figma-to-guiguider-controlled-sync/scripts/audit_guiguider_project.py \
  --project project/guiguider_2.0.guiguider
```
