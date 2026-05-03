# Studio Lab OS — CLI Reference

> Arc B.3. Covers `cgl-orient` (B.2) and `cgl-claw` (B.3) including the new
> orientation-driven spawn mode. For full Lab OS architecture see
> `docs/specs/studio-lab-os-spec.md`.

---

## `cgl-orient`

Manages orientation files in a lab's `.studio/orientations.toml`. All
subcommands require `CGL_LAB_ROOT` to be set.

### `cgl-orient list`

**Synopsis:** `cgl-orient list`

Lists all orientations defined in `.studio/orientations.toml`.

**Output:** One line per orientation, showing the ID and status.

**Exit codes:** 0 on success, 1 if the config cannot be loaded.

**Example:**

```
$ CGL_LAB_ROOT=examples/hello-lab cgl-orient list
orient-hello-lab-studio-exploration  draft
```

---

### `cgl-orient show <id>`

**Synopsis:** `cgl-orient show <id>`

Prints the full details of an orientation by ID.

**Flags:** None.

**Exit codes:**
- 0 — orientation found and printed
- 1 — orientation ID not found (stderr: "not found")

**Example:**

```
$ CGL_LAB_ROOT=examples/hello-lab cgl-orient show orient-hello-lab-studio-exploration
id:        orient-hello-lab-studio-exploration
objective: Explore the Studio repo structure and document how the lab OS primitives fit together.
roles:     scout, researcher, curator
status:    draft
...
```

---

### `cgl-orient validate`

**Synopsis:** `cgl-orient validate`

Validates `.studio/orientations.toml` (and related config files) for structural
correctness. Does not test runtime connectivity.

**Exit codes:**
- 0 — config valid (stdout: "ok: ...")
- 1 — validation error (stderr: details)

**Example:**

```
$ CGL_LAB_ROOT=examples/hello-lab cgl-orient validate
ok: orientations.toml is valid (1 orientation)
```

---

### `cgl-orient create`

**Synopsis:** `cgl-orient create [options]`

Creates a new orientation entry in `.studio/orientations.toml`. Interactive or
flag-driven depending on the implementation.

See `bin/cgl-orient` for the full flag set.

---

## `cgl-claw spawn --orientation` (new orientation-driven mode)

**Synopsis:**

```
cgl-claw spawn --orientation <id> --role <role> --dry-run
```

Dry-runs a role-based claw against an orientation. Validates the orientation
and role, then writes a stub artifact bundle to `.claws/<bundle-id>/` inside
the lab. Does not execute `claude` or any subprocess.

### Flags

| Flag | Required | Description |
|---|---|---|
| `--orientation <id>` | yes | Orientation ID from `.studio/orientations.toml` |
| `--role <role>` | yes | One of: `scout`, `researcher`, `builder`, `reviewer`, `operator`, `curator` |
| `--dry-run` | yes (Arc B) | Write stub bundle only. Real spawn arrives in Arc C. |

### Validation

Before writing, the command checks:

1. `CGL_LAB_ROOT` is set and is a directory.
2. `.studio/orientations.toml` can be loaded and the orientation ID exists.
3. The role is a valid Studio role.
4. The role appears in the orientation's `roles` list. If not, exits 1 with a
   message that names the disallowed role and lists the permitted roles.

### What gets written

A new directory at `.claws/<YYYYMMDD-HHMMSS-<role>-<lab-slug-safe>>/` containing:

| File | Description |
|---|---|
| `meta.json` | Run metadata. `"status": "dry_run"`. See `docs/specs/artifact-bundle.md` for field reference. |
| `trace.jsonl` | Trace log. First line has `"event": "dry_run"`. |
| `result.md` | Human-readable stub noting this is a dry-run bundle. |

The bundle directory name follows the format defined in `docs/specs/artifact-bundle.md` §ID Format.

### What does NOT happen

- `claude` is not executed.
- No worktree or branch is created.
- No network calls are made.
- Capability gateway enforcement is not applied (Arc C).
- The bundle is not submitted to a promotion queue (Arc C).

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Bundle written successfully. Envelope JSON printed to stdout. |
| 1 | Config load error, orientation not found, or role not permitted by orientation. |
| 2 | `--dry-run` was not supplied (real spawn is not implemented in Arc B). |

### Example invocation

```
$ CGL_LAB_ROOT=examples/hello-lab cgl-claw spawn \
    --orientation orient-hello-lab-studio-exploration \
    --role scout \
    --dry-run
{
  "id": "20260501-153000-scout-hello-lab",
  "orientation_id": "orient-hello-lab-studio-exploration",
  ...
}
```

Files created:

```
examples/hello-lab/.claws/20260501-153000-scout-hello-lab/
  meta.json
  trace.jsonl
  result.md
```

See `docs/specs/artifact-bundle.md` for the full bundle contract.

---

## Existing subcommands (brief reference)

### `cgl-claw spawn <slug> "<task>"`

The original positional spawn mode. Spawns a `claude -p` worker in a new git
worktree branched from the lab's current HEAD. The worktree lives at
`trees/claw/<slug-safe>-<ts>/`; logs and result land at
`<lab>/.claws/<ts>.{log,result.md}`. This path is **entirely unchanged** by Arc
B. See the script header in `bin/cgl-claw` for full detail.

### `cgl-claw list <slug>`

Lists claws for a lab (status: running/done/merged/abandoned) ordered by
timestamp. See `bin/cgl-claw` for output format.

### `cgl-claw tail <slug>`

Tails the most recent claw log for a lab in real time. Exits when the process
exits. See `bin/cgl-claw`.

### `cgl-claw merge <slug> <ts>`

Rebases the claw's branch onto the lab's main branch, fast-forward merges into
main, removes the worktree, and optionally syncs to `CGL_DEPLOY_PATH` if
configured. See `bin/cgl-claw`.

### `cgl-claw abandon <slug> <ts>`

Removes the claw's worktree and branch without merging. Marks meta status as
`abandoned`. See `bin/cgl-claw`.

---

### Other `cgl-*` commands

| Command | Description |
|---|---|
| `cgl-arm` | Manage long-lived git worktree arms (`new`, `merge`, `kill`, `list`). See `bin/cgl-arm`. |
| `cgl-bridge` | Launch the Bridge TUI (director console). Requires the textual venv. See `bin/cgl-bridge`. |
| `cgl-focus` | Produce a director HUD snapshot for a lab (text, JSON, or `--rollup` with Haiku condensing). See `bin/cgl-focus`. |
| `cgl-lab` | Launch the Lab TUI for a specific lab slug. See `bin/cgl-lab`. |
| `cgl-labs` | Manage labs: `new`, `archive`, `restore`, `list`. See `bin/cgl-labs`. |
| `cgl-supervisor` | Manage persistent Claude supervisor sessions: `activate`, `session-id`, `list`. See `bin/cgl-supervisor`. |
| `cgl-tell` | Inject a message into a lab's supervisor tmux pane. See `bin/cgl-tell`. |
| `cgl-themes` | Run the theme extraction pipeline for a lab (`--reflect`). See `bin/cgl-themes`. |
| `cgl-tmux` | Launch the federation tmux session. Idempotent; attaches if already running. See `bin/cgl-tmux`. |

---

## Not yet implemented (Arc B scope boundary)

The following are outside Arc B and will arrive in Arc C or later:

- **Real orientation-driven claw spawn.** `--dry-run` is required in Arc B.
  Actual `claude` execution via an orientation is Arc C (`cgl-claw spawn
  --orientation ... --role ...` without `--dry-run`).
- **Capability gateway enforcement.** Role and capability policies are declared
  in `.studio/capabilities.toml` and `roles.toml` but are not enforced at
  runtime. Arc B validates role membership in the orientation only.
- **Promotion queue integration.** Bundles are written but not surfaced in the
  Bridge promotion queue. Arc C / Arc D.
- **Source pack acquisition.** Sources defined in `sources.toml` are not fetched
  or validated in dry-run mode.

Reference: `docs/lab-os.md` for the full Arc roadmap.
