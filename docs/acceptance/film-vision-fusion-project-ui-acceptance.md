# Film Vision Fusion project UI acceptance

Date: 2026-08-30
Implementation baseline: `0f7865c`
Acceptance target: P0 plus Slice 0–7 in `ready-for-agent-film-vision-fusion-project-workspace-ui.md`

## Automated state and safety coverage

The project projection test covers these creator-facing states with deterministic
precedence: `draft`, `running`, `interrupted`, `waiting_for_review`, `blocked`,
`ready_to_render`, `completed`, `source_offline`, `stale_result`, `archived`, and
`trashed`.

The focused project/UI suite also verifies:

- durable project create/read/update, rename, archive, trash, restore, and explicit migration;
- local-reference versus managed-asset ownership and source reconnection;
- project/source task ownership, restart reconciliation, safe diagnostics, and stale-result admission;
- Content Draft impact and version creation;
- Plan validation, approval, matching, Narrative Map review, synchronized review context, bounded timeline edits, and version restore;
- Render Preflight blocker/warning policy, immutable Render Outcomes, and frozen render configuration snapshots;
- default Project Library navigation and removal of stale Film Vision Fusion state before entering traditional modes.

The post-review full discovery run completed **272 tests successfully** with one
provider/environment test skipped. It additionally verifies that a source file
replaced at the same path invalidates old evidence, concurrent project-task
updates are serialized, complete Plan responses remain recoverable, legacy
imports cannot inherit render authority, and a render completed for an older
version is retained only as a stale outcome. The same coverage also verifies
atomic task reservation, run-token isolation after cancel/retry, media-content
hash identity, and the safe legacy revalidation path.

## Responsive visual inspection

Reference views were captured and inspected in the local Codex in-app browser
against a fresh Streamlit process.

| Viewport | Result | Horizontal overflow | Notes |
| --- | --- | --- | --- |
| 1440 × 900 | Pass | None | Shared shell, search/filter row, three project cards, and actions remain aligned. |
| 1080 × 800 | Pass | None (`scrollWidth = clientWidth = 1080`) | Three-card layout remains readable and actions remain visible. |
| 1024 × 768 | Pass | None (`scrollWidth = clientWidth = 1024`) | Search/filter row and project cards remain usable at the minimum specified width. |

The page was also checked after switching from New Project to Traditional Modes.
After Streamlit completed its rerun, the project configuration was absent and
the legacy Film Vision Fusion settings were not rendered.

## Accessibility inspection

- Main dark-theme text and card metadata measured between 6.04:1 and 16.91:1.
- The primary button was darkened from `#4f83f1` to `#3568d4`; white text now measures approximately 5.14:1.
- Forty-eight visible, enabled application controls use native focusable elements and expose text, placeholder, or an accessible name.
- The only audit exception is Streamlit's intentionally clipped file-input implementation (`tabindex=-1`), which is operated through its visible upload control.
- No horizontal overflow was observed at the required viewports.

## State evidence

The full state matrix is recorded by
`FusionProjectStoreTests.test_project_projection_covers_creator_facing_state_matrix`.
The browser pass directly covered the Project Library empty/working surface,
project cards, explicit migration entry, new-project setup, managed upload,
traditional-mode routing, and responsive shell. Running, waiting, blocked,
ready, completed, offline, interrupted, and stale-result semantics are covered
by durable projection tests and their corresponding task/output gates.

## Real-media gate

This repository does not contain the source movie, subtitle, provider logs, or
finished sample required to truthfully complete a real-media usability run.
Therefore Slice 7's code and visual acceptance are complete, but the release
must remain **not real-media accepted** until at least one creation-to-render
sample is completed, followed by the broader three-classes-by-two set in
`film-vision-fusion-real-media-manifest.md`.

Do not replace this gate with mocked media or unit-test success. Complete the
manifest using local secure paths and human viewing scores before migration
cutoff or production release.
