---
layer: spec
type: build-plan
status: draft — awaiting director review before any implementation
created: 2026-05-01
branch: tui/build
spec: docs/specs/tui-director-cockpit-spec.md
lab-os-spec: docs/specs/studio-lab-os-spec.md
---

# TUI Director Cockpit — Build Plan

This document translates `tui-director-cockpit-spec.md` into a concrete,
reviewable build plan. Nothing here is implemented. It is the artifact the
team lead reads before committing to any arc.

---

## 1. Inventory

### 1.1 Primary screens — what the spec actually requires

**Screen 1: Federation Home** (spec section 6)

The default director view across all labs. It is a three-column layout: a
Labs list on the left (slug, kind, orientation summary, status indicator),
a Director Queue in the center (needs review, active decisions, stale labs),
and Cross-Lab Intelligence on the right (emerging patterns, shared source
packs, risks). Each lab row carries a typed status—active, idle, blocked,
stale, or needs_review—expressed through plain-text symbols (●, ◐, !, ○, …)
and never through color alone. The minimum viable version must render at
least one lab row from file-backed state and distinguish implemented
behaviour from spec-only placeholders. Data comes from `.studio/lab.toml`,
`.studio/orientations.toml`, and `.claws/` artifact bundles inside each lab
directory.

**Screen 2: Lab Focus** (spec section 7)

A drill-down into one lab. It shows the current orientation (objective,
sources, stop rule), supervisor session status, claws grouped by
role/status in workflow order (scout → researcher → builder → reviewer →
operator → curator), recent themes from `.intel/themes/<slug>.jsonl`, and
promotion candidates awaiting the director's decision. The director steers
the lab from this screen using action keys: `o` (orient), `s` (spawn role),
`r` (review), `p` (promote), `f` (back to federation). Data is read from
`.studio/orientations.toml`, `.studio/roles.toml`, `.claws/<id>/meta.json`,
and `.intel/themes/`.

**Screen 3: Promotion Review** (spec section 8)

The most important screen in the spec. It renders one promotion candidate in
full: artifact bundle file listing (meta.json, result.md, evidence.jsonl,
trace.jsonl), verification check results (provenance present, no code
execution, claims reviewed, reviewer pass), a human-readable result summary,
and a decision bar (abandon / keep evidence / continue / merge / publish /
graduate to spine). The first implementation may display only and not
mutate—mutations dispatch to `cgl-*` primitives later. Data comes from
`.claws/<id>/` directories and a promotion_recommendation field in meta.json.

**Screen 4: Capability Request** (spec section 9)

An inspect-before-act screen. It renders a proposed claw's capability
envelope: role, capability profile name, runtime, allowed tools, denied
capabilities, and whether director approval is required. The first
implementation is display-only and file-backed—it reads
`.studio/capabilities.toml` and `.studio/roles.toml`. No enforcement is
required at this stage; the spec explicitly permits declarative-only
modelling in v0.

**Screen 5: Chat / Command Pane** (spec section 10)

A contextual director conversation surface. It must carry an explicit scope
(Federation, Lab, Artifact, Capability, Source Pack) which determines what
context is loaded. Chat responses should produce action cards with proposed
next steps, not free-form prose. The spec permits reserving the layout space
and documenting command equivalents if full chat is not implemented in the
first pass—making this the one screen that may be a placeholder initially.

---

### 1.2 State the TUI needs to read — data source map per screen

| Screen | Primary files | Secondary files | Notes |
|---|---|---|---|
| Federation Home | `.studio/lab.toml` per lab | `.studio/orientations.toml`, `.claws/*/meta.json` | Lab status derived from meta.json artifact counts |
| Lab Focus | `.studio/orientations.toml`, `.studio/roles.toml` | `.claws/*/meta.json`, `.intel/themes/<slug>.jsonl` | Supervisor session from supervisors.json (existing) |
| Promotion Review | `.claws/<id>/meta.json`, `.claws/<id>/result.md` | `.claws/<id>/evidence.jsonl`, `.claws/<id>/trace.jsonl` | promotion_recommendation in meta.json |
| Capability Request | `.studio/capabilities.toml`, `.studio/roles.toml` | `.studio/runtimes.toml` | Display-only; no enforcement |
| Chat Pane | Scope-dependent context from above | Supervisor session log (optional) | Placeholder acceptable in Arc 1 |

**Missing fixtures in `examples/hello-lab/`:** The hello-lab directory
currently contains only a README and an empty directory scaffold. It has no
`.studio/` files, no `.claws/` artifacts, and no `.intel/themes/` data.
Before any TUI screen can render against it, sample fixture files must be
created. This is a prerequisite for every arc.

---

### 1.3 Explicit out-of-scope items (spec section 16)

The following are stated non-goals and must not appear in any arc:

- Web UI or mobile UI of any kind
- Daemon, background scheduler, or cron process
- Database (SQLite, Postgres, or otherwise)
- Web crawlers or external API integrations at runtime
- Credential broker or secret management
- Actual container sandboxing or runtime enforcement of capability gates
- Model/provider routing logic
- Auto-merge or auto-publish (director must always decide)
- Rebranding Studio as a generic session runner

Additionally, the following are out of scope for this branch specifically,
even though the lab-os spec mentions them:

- Bellclaw passive listener
- Unified ledger writer
- Lifecycle gates / promotion-stage enforcement
- Source pack connector implementation
- Multi-studio / commons layer

---

## 2. Existing code reuse

### 2.1 What can be reused

**`studio/lib/state_reader.py`** — Keep, extend. The typed dataclasses
(`Lab`, `LedgerRow`, `SpineAsset`, `Contract`, `StudioSnapshot`,
`LabSnapshot`) and the file-reading helpers (`_read_json`, `_read_jsonl`,
`_parse_dt`, `_rot_color`) are directly reusable. The lab discovery
functions (`list_surfaces`, `list_investigations`, `list_systems`) provide
the foundation for Federation Home's lab list. The `get_lab` and
`list_contracts` functions carry over unchanged.

What needs to be added to `state_reader.py` (or a new `loaders.py`):
- `read_orientation(lab_path)` — parse `.studio/orientations.toml`
- `read_capabilities(lab_path)` — parse `.studio/capabilities.toml`
- `list_artifact_bundles(lab_path)` — enumerate `.claws/<id>/meta.json`
- `read_artifact(bundle_path)` — load one complete artifact bundle
- `list_promotion_candidates(lab_path)` — filter bundles by promotion_recommendation
- `read_themes(lab_slug)` — parse `.intel/themes/<slug>.jsonl`
- Graceful degradation for every loader when files are absent

**`studio/bridge/app.py` — LabsPane**. The list rendering pattern (cursor
tracking, j/k/enter navigation, status colour markers) is directly
applicable to the new Federation Home lab list. The `cursor_idx` /
`active_idx` dual-index model is clean and should be preserved. The
`refresh_data` / `set_interval` polling pattern should be kept as-is.

**`studio/bridge/app.py` — FocusPane (partial)**. The `DataTable`-based
row rendering with row metadata (`_row_meta` dict) is a good pattern for
the artifact list in Lab Focus and the file listing in Promotion Review. The
federation section of `_render_federation_view` is much closer to what the
new Federation Home needs than the current per-lab focus view is. Reuse the
section-header-rows-in-DataTable technique.

**`studio/bridge/app.py` — BridgeApp keybindings and tmux integration**.
The tmux pane-switching logic (`_activate_supervisor`, `_park_pane`,
`_unpark_pane`) should be preserved unchanged. Navigation bindings (j/k,
enter, `[`/`]`, `f`) align well with the spec's suggested keymap.

**`studio/lab_tui/app.py`** — The `LabCard` widget pattern (a `Static`
with `refresh_data`) is the right shape for the Lab Focus orientation block.
The `ContractsPane` / `ArtifactsPane` column layout is reusable as a
structural template. However, the specific data these widgets show (ledger,
contracts) will be replaced with orientation, roles, and artifact bundles.

**`studio/lib/focus_core.py`** — The `tail_session` function for reading
Claude session logs is reusable in Lab Focus for supervisor session status.
The URL probing logic (`probe_url`) is not needed in this TUI scope.

**`bin/cgl-bridge` and `bin/cgl-tmux`** — No changes needed. The new TUI
should be launchable via a new `bin/cgl-cockpit` script that follows the
same pattern as `cgl-bridge`.

### 2.2 What needs replacing or major extension

**`studio/bridge/app.py` — FocusPane (the rest)**. The Haiku rollup
worker, the `cgl-themes --reflect` spawning, the federation pipeline
`_reflect_stale_labs`, and the supervisor context builder are all specific
to the existing v0 approach (session-log-based summaries). These do not map
to the new `.studio/`-file-based orientation model and should be removed or
gated behind a feature flag.

**`studio/lab_tui/app.py` — ContractsPane**. Contracts are the v0 concept
for what orientations are in the new spec. The new Lab Focus does not use
the `CONTRACT.yaml` / `list_contracts()` path; it reads
`.studio/orientations.toml` instead. The pane widget shape can be reused
but its data source changes.

**`studio/lib/state_reader.py` — `Lab` dataclass**. The current `Lab` lacks
`orientation_id`, `orientation_summary`, `active_claws` (count, not bool),
`unreviewed_artifacts`, `promotion_candidates`, `blockers`, and `next_action`
fields required by the spec's `LabStatus` data model (section 13.1). The
dataclass needs extending. Existing consumers of the old fields continue to
work.

### 2.3 Framework compatibility with Textual

The spec is fully compatible with Textual. Every screen layout the spec
describes maps cleanly to Textual's `Horizontal`, `Vertical`, `DataTable`,
`Static`, and `RichLog` widgets. The spec does not imply any web, reactive,
or event-bus architecture that would require a different framework. The
existing Textual patterns (screen mounting, `compose()`, `on_mount()`,
`set_interval()`, `run_worker()`, `call_from_thread()`) are all appropriate
for the new screens.

One Textual feature worth adopting: `App.push_screen()` / `pop_screen()` for
the Federation → Lab Focus → Promotion Review navigation hierarchy. The
existing bridge uses a single `App` with view-mode toggling; the new cockpit's
deeper navigation model (3 levels: Federation → Lab → Artifact) is cleaner
as proper screen stacks in Textual, which has native support for this.

The spec's CSS requirements (warm dark background `#1c1917`, amber borders
`#c5b08a`, status colors) are identical to the existing bridge theme. Reuse
the existing CSS block with additions for new widgets.

---

## 3. Build phases

### Arc 1 — Fixtures and loaders foundation
**One-line description:** Create the example `.studio/` and `.claws/`
fixture files in `examples/hello-lab/` and build the typed loaders that
read them.

**Deliverables:**
- `examples/hello-lab/.studio/lab.toml` — lab identity, kind, paths
- `examples/hello-lab/.studio/orientations.toml` — one draft orientation
- `examples/hello-lab/.studio/roles.toml` — all six role definitions
- `examples/hello-lab/.studio/capabilities.toml` — research_readonly and build_worktree profiles
- `examples/hello-lab/.studio/runtimes.toml` — claude and claude_print entries
- `examples/hello-lab/.studio/promotion.toml` — allowed outcomes and candidate types
- `examples/hello-lab/.studio/sources.toml` — at least one source entry
- `examples/hello-lab/.claws/20260501-150000-scout-example/meta.json` — one finished scout artifact
- `examples/hello-lab/.claws/20260501-150000-scout-example/result.md` — narrative result
- `examples/hello-lab/.claws/20260501-150000-scout-example/evidence.jsonl` — 3 sample claims
- `examples/hello-lab/.claws/20260501-150000-scout-example/trace.jsonl` — 4 sample trace events
- `examples/hello-lab/.intel/themes/hello-lab.jsonl` — 3 sample theme events
- `studio/tui/loaders.py` — new module with all read functions listed in section 1.2
- `studio/tui/models.py` — `LabStatus`, `ArtifactSummary`, `PromotionCandidate`, `CapabilityRequest` dataclasses (per spec section 13)
- `tests/test_loaders.py` — tests for all loader functions against hello-lab fixtures, including missing-file graceful degradation

**Acceptance criteria:**
- `python -m pytest tests/test_loaders.py` passes with no real lab data, only `examples/hello-lab/`
- Every loader returns a typed empty result (not an exception) when its target file is absent
- `loaders.list_artifact_bundles(hello_lab_path)` returns exactly one bundle
- `loaders.list_promotion_candidates(hello_lab_path)` returns the scout artifact (recommendation is `keep_evidence`)
- `loaders.read_capabilities(hello_lab_path)` returns `research_readonly` and `build_worktree` profiles

**Estimated complexity:** M

**Dependencies:** None. This arc is fully self-contained and does not depend
on any lab-os-migration branch work.

---

### Arc 2 — Federation Home screen
**One-line description:** Render a working Federation Home screen with a
live lab list, status indicators, and the Director Queue panel, backed by
the Arc 1 loaders.

**Deliverables:**
- `studio/tui/app.py` — new `CockpitApp` class replacing `BridgeApp` as the entrypoint, or extending it
- `studio/tui/screens/federation.py` — `FederationScreen` (Textual `Screen` subclass)
- `studio/tui/widgets.py` — `LabListPane`, `DirectorQueuePane`, `CrossLabPane` widgets
- Updated `bin/cgl-cockpit` launcher script following the `cgl-bridge` pattern
- Updated `studio/lib/state_reader.py` — `Lab` dataclass extended with `LabStatus` fields
- Visual status vocabulary implemented: ●, ◐, !, ○, …, ✓ (spec section 6.4)
- `tests/test_federation_screen.py` — smoke tests with hello-lab as CGL_LAB_ROOT

**Acceptance criteria:**
- `CGL_LAB_ROOT=examples/hello-lab cgl-cockpit` launches without error or traceback
- Federation Home renders at least one lab row from hello-lab fixtures
- Status indicator (●/◐/!/○/…) appears correctly for the sample lab based on meta.json state
- Director Queue section shows the scout artifact as a promotion candidate
- j/k navigation moves cursor through lab rows; Enter does not crash
- `f` key toggles between Federation and a placeholder Lab Focus (may show "not yet implemented")
- TUI exits cleanly on `q`

**Estimated complexity:** M

**Dependencies:** Arc 1 (loaders and fixtures must exist).

---

### Arc 3 — Lab Focus screen
**One-line description:** Implement the Lab Focus screen showing
orientation, role-based claw workflow, themes feed, and artifact list for
the selected lab.

**Deliverables:**
- `studio/tui/screens/lab_focus.py` — `LabFocusScreen` (Textual `Screen`)
- `studio/tui/widgets.py` additions — `OrientationPane`, `RoleWorkflowPane`, `ThemesFeedPane`, `ArtifactListPane`
- Navigation wired: `Enter` on a lab row in Federation Home pushes `LabFocusScreen`; `Escape`/`b` pops back
- Role workflow display: scout / researcher / builder / reviewer / operator / curator with status per active artifact
- Themes feed reads `.intel/themes/<slug>.jsonl` (reuses existing `_refresh_events` pattern from bridge)
- Action key stubs: `o` (orient — shows notify "not yet wired"), `s` (spawn — notify), `r` (review — pushes Promotion Review if candidate exists), `p` (promote — notify)

**Acceptance criteria:**
- Entering a lab from Federation Home pushes Lab Focus without crash
- Orientation block shows objective and stop_rule from `.studio/orientations.toml`
- Role workflow table shows at least one row (scout: done) derived from the hello-lab artifact
- Themes feed shows the 3 sample themes from `.intel/themes/hello-lab.jsonl`
- Artifact list shows the single scout artifact with its status and promotion recommendation
- Escape returns to Federation Home
- Missing `.studio/orientations.toml` shows a "(no orientation)" hint, not a traceback

**Estimated complexity:** M

**Dependencies:** Arc 1 (loaders), Arc 2 (navigation model and CockpitApp).

---

### Arc 4 — Promotion Review and Capability Request screens
**One-line description:** Implement the two decision screens—Promotion Review
for artifact/evidence judgement and Capability Request for claw permission
inspection—both display-only and backed by file state.

**Deliverables:**
- `studio/tui/screens/promotion_review.py` — `PromotionReviewScreen`
- `studio/tui/screens/capability_request.py` — `CapabilityRequestScreen`
- `studio/tui/widgets.py` additions — `ArtifactBundlePane`, `VerificationPane`, `DecisionBar`, `AllowedDeniedPane`
- `studio/tui/actions.py` — stub action dispatchers for promotion decisions (log decision to a local decisions file, or shell out to `cgl-*` primitive if it exists; no silent mutation)
- Navigation: `r` on an artifact in Lab Focus pushes Promotion Review; `c` on a blocked item pushes Capability Request
- Verification checks computed from meta.json fields: provenance_present, no_code_execution, claims_reviewed, reviewer_pass
- Decision bar renders all six outcomes (abandon / keep evidence / continue / merge / publish / graduate to spine) with key hints; keys that would mutate are stubbed with a "not yet wired" notify until dispatchers exist

**Acceptance criteria:**
- Promotion Review renders for the hello-lab scout artifact without crash
- Artifact bundle file list shows meta.json, result.md, evidence.jsonl, trace.jsonl
- Verification panel shows at least two checks with correct pass/fail status
- Result summary renders from `result.md` (first 800 chars)
- Decision bar is visible; pressing `k` (keep evidence) on the stub shows a notify rather than crashing
- Capability Request renders `research_readonly` profile from `capabilities.toml`
- Allowed/denied columns correctly split from capabilities.toml entry
- Escape pops back to Lab Focus from both screens

**Estimated complexity:** L

**Dependencies:** Arc 1 (loaders and fixtures), Arc 2 (CockpitApp, screen stack), Arc 3 (Lab Focus as navigation parent).

---

### Arc 5 — Navigation wire-up, Chat pane placeholder, and smoke polish
**One-line description:** Wire the complete navigation graph, add the Chat /
Command Pane as a scoped placeholder, implement the full keymap from the
spec, and add an install smoke-test runbook.

**Deliverables:**
- Full keymap wired per spec section 11: `f`, Enter, Escape, j/k, `/`, `o`, `s`, `r`, `p`, `a`, `e`, `tr`, `c`, `?`, `q`
- `studio/tui/screens/chat.py` — `ChatPane` as a scoped static placeholder; scope label renders (Federation / Lab / Artifact / Capability); input box present but stubs with a "chat not yet implemented" notify on submit; reserves correct layout real estate
- `?` key shows a help overlay listing all keybindings and their status (implemented vs. spec-only)
- All spec-only/future features are marked in the UI with a `[spec-only]` dim suffix rather than being silently absent or crashing
- `docs/runbooks/tui-smoke-test.md` — runbook for verifying the TUI against hello-lab, including exact environment variables to set
- `README` updates limited to the TUI section (add launch instructions for `cgl-cockpit`)

**Acceptance criteria:**
- Full end-to-end navigation path works: launch → Federation Home → select lab → Lab Focus → select artifact → Promotion Review → Escape → Escape → Federation Home
- Capability Request is reachable from a blocked lab row (test with a hand-edited hello-lab fixture adding a blocker)
- `?` overlay renders and dismisses cleanly
- Chat pane renders scope label when entering each screen; does not crash when text is typed and Enter pressed
- `CGL_LAB_ROOT=examples/hello-lab cgl-cockpit` followed by the full smoke-test runbook completes without error on a clean install

**Estimated complexity:** M

**Dependencies:** Arcs 1-4 complete.

---

## 4. Open questions

These must be resolved by a director call before the relevant arc begins.
The question number maps loosely to which arc it blocks.

**Q1 (blocks Arc 1): Where does `.studio/` live — lab root or federation root?**

The lab-os spec (section 18) explicitly names this as an open question: "Should
`.studio` live inside each lab or at the federation root with per-lab
sections?" The TUI spec's data model (section 12) shows paths like
`.studio/lab.toml` without resolving which root that is relative to. In the
current v0, `examples/hello-lab/` IS the lab root and would be the natural
home for `.studio/`. But if the federation root is distinct from any individual
lab (e.g., the harness root rather than a lab directory), the loader paths
change entirely. The loaders in Arc 1 cannot be written with confidence until
this is settled.

**Q2 (blocks Arc 2): Is the new cockpit a replacement for `cgl-bridge` or an
addition alongside it?**

The spec says "if existing TUI code exists, adapt it rather than replacing it
wholesale" (section 14.1). The existing `BridgeApp` in `studio/bridge/app.py`
has significant working tmux supervisor-switching logic, ledger rendering, and
federation inbox views that the new TUI does not yet replicate. Two paths are
possible: (a) extend `BridgeApp` in-place with new screens, preserving all
tmux wiring; or (b) build a new `CockpitApp` that starts fresh but initially
lacks tmux supervisor activation. Path (a) is safer but messier; path (b) is
cleaner but loses the supervisor-switching capability until explicitly rebuilt.
The director needs to decide which existing Bridge capabilities are load-bearing
before Arc 2 starts.

**Q3 (blocks Arc 4): What does a promotion decision actually do in v0?**

The spec says "initial implementation may only display and not mutate" but also
says "mutation can dispatch to primitives later" (section 8.5). As of this
branch, there are no `cgl-promote`, `cgl-keep-evidence`, or `cgl-abandon`
primitives in `bin/`. The closest is `cgl-claw abandon` and `cgl-claw merge`
in the existing bridge. The Promotion Review screen in Arc 4 needs to do
something when the director presses a decision key—even if that something is
writing a decision record to a local file. Before Arc 4, the team needs to
agree: (a) decisions write to a `decisions/` file and the director shells out
manually; (b) decisions shell out to whichever `cgl-*` primitive exists; or
(c) decisions are purely display-only with no state change, with a visible
warning that nothing was persisted. Option (c) is safe but may confuse
directors who believe they acted.

**Q4 (blocks Arc 3): Is the supervisor session-log integration (focus_core.py)
still needed in Lab Focus?**

The existing `FocusPane` pulls director/assistant conversation excerpts from
Claude session log files (`~/.claude/projects/.../uuid.jsonl`) via
`focus_core.tail_session()`. The new Lab Focus spec does not mention session
logs as a data source—it reads `.intel/themes/` instead. However, the themes
feed may be empty for new or lightly-used labs. Before building the themes
integration, confirm: should Lab Focus fall back to session logs if themes are
absent, or should it show an empty themes feed and a setup hint only?

**Q5 (ambiguous throughout): How should the TUI handle a lab directory that
has no `.studio/` files at all?**

The spec says "missing `.studio/` should not crash the TUI. Show a setup
hint" (section 14.2). It does not specify what constitutes a valid lab for
the purposes of the Federation Home list. The current `state_reader.py`
discovers labs by looking for `surfaces/`, `research/investigations/`, and
`systems/` subdirectories with README files. If a lab directory exists and is
discovered by that mechanism but has no `.studio/` directory, the TUI should
render it—but as what status? "idle" by default? "unconfigured"? This
affects both the lab list row display and the LabStatus data model. The
`hello-lab` fixture currently has no `.studio/` directory either, so the
answer to this question determines whether Arc 2's acceptance criteria are
testable at all without first creating fixtures.

---

## 5. Recommendation

**Build Arc 1 first.**

Arc 1 is the only arc with no dependencies and the one that unblocks every
other arc. Without the hello-lab fixture files, no screen can be tested
against real data. Without typed loaders that degrade gracefully on missing
files, every screen render is fragile. The spec itself says "add tests for
loaders and state model before heavy UI tests" (section 14.4) and the
recommended build sequence in section 17 places fixture creation first.

Arc 1 is also the smallest demonstrable slice that proves the architecture:
running `pytest tests/test_loaders.py` with hello-lab as the fixture root
validates the entire data model—`LabStatus`, `ArtifactSummary`,
`PromotionCandidate`, `CapabilityRequest`—before a single pixel of TUI is
rendered. That is the right place to find schema disagreements between the
spec and what file-backed state can actually provide.

The director call before Arc 1 starts should answer Q1 (where does
`.studio/` live) and Q5 (how to classify a lab without `.studio/` files).
Those two answers take under an hour to resolve and unlock the entire plan.
After Arc 1 ships with green tests, Arc 2 is immediately buildable and can
be reviewed as a standalone demo (launch, see one lab row, quit) without
waiting for Arc 3 or beyond.

The most important architectural bet in the whole plan is the Textual
`Screen` stack for navigation (Arc 2). If Textual's `push_screen` /
`pop_screen` behaves cleanly under the three-level Federation → Lab →
Artifact hierarchy, the rest of the navigation model follows naturally. Arc 2
is where that bet is placed; it deserves a deliberate review before Arc 3
begins.
