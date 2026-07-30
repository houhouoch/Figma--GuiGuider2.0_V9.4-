# GUI Guider 2.0 Opens the Old Project When Project IDs Collide

## Status

- Defect condition: **verified**
- Local preparation fix: **verified**
- Manual delete/save/close/reopen test with the new identity: **pending**
- Date: 2026-07-30

## Symptom and impact

After copying or publishing a `.guiguider` project, GUI Guider 2.0 may continue
opening the old project even when the user selects the new file. A deleted
widget then appears again after reopening, which looks like a read-only or
locked project.

This can send edits and generated code to the wrong project and makes visual
review unreliable.

## Reproduction conditions

The issue is reproducible when:

1. a project is copied to another directory;
2. both copies retain the same `projectId`;
3. GUI Guider history still associates that identity with the old path; and
4. the new file is opened through a shortcut, double click, or an existing
   single-instance process.

Changing only the filename or `projectPath` does not create an independent
GUI Guider project identity.

## Evidence

The old formal project and the first public local copy both contained:

```text
projectId = project-MRWWUBKD5NV0
```

The GUI Guider process command line and
`%APPDATA%\GUIGuider\2.0.0\project_history.json` resolved to the old formal
path. The target files were not read-only, their ACLs allowed modification, a
read/write handle opened successfully, and no `EACCES`, `EPERM`, project-level
lock field, or save error was found.

## Direct and root causes

The direct cause was a duplicate internal `projectId`. GUI Guider's recent
project and single-instance behavior treated the files as the same project and
continued resolving the old path.

The root cause in this repository was that `prepare_local_project.py` replaced
only `projectPath` and allowed existing output to be overwritten.

This is both an opaque GUI Guider 2.0 product limitation/defect and a missing
identity-isolation gate in the local preparation workflow.

## Failed approaches

- Renaming or moving the file: internal identity remained unchanged.
- Changing only `projectPath`: the duplicate `projectId` remained.
- Clearing file read-only state: file permissions were not the cause.
- Starting GUI Guider from its shortcut: it restored the recent old project
  and did not prove that the target file was loaded.

## Final solution

Commit `d78232159ab7c67b1ab95a103bd29787045f63be`:

- derives a clone-specific `projectId` from the project name and absolute
  output path;
- uses the explicit local name `Figma_GuiGuider2_V9_4_local`;
- sets the local absolute `projectPath`;
- refuses to overwrite an existing local project by default;
- requires `--force` for an intentional rebuild;
- adds a regression test for identity isolation; and
- documents the behavior in both READMEs.

## Verification

Verified:

- five controlled-sync tests passed, with one external-asset test skipped;
- repository validation passed;
- GUI Guider read-only audit passed;
- 34 entries, 1,735 objects, and 50 complete resources;
- different output directories produce different IDs;
- the new ID differs from the formal project;
- overwrite protection rejects an existing output; and
- GitHub Actions `Validate` passed.

Pending manual confirmation:

1. close GUI Guider completely;
2. open the newly prepared local file;
3. confirm the project name is `Figma_GuiGuider2_V9_4_local`;
4. delete a recoverable test widget;
5. save with `Ctrl+S`;
6. close and reopen the exact same file; and
7. confirm that the deletion persists.

## Prevention checklist

- Require distinct `projectId`, `projectName`, and `projectPath` values for
  formal, candidate, review, and clone projects.
- Never treat a different filename as project isolation.
- Verify the visible project name and page tree after opening.
- Inspect GUI Guider project history when the wrong project is restored.
- Always include save/close/reopen in manual persistence testing.
- Do not overwrite an existing local project unless the user explicitly
  requests a rebuild.
