# Studio Cockpit — lab_tui

Federation home screen for the Studio director.

## How to run

```
CGL_LAB_ROOT=examples/hello-lab bin/cgl-cockpit
```

Or pass the lab root as an argument (CGL_LAB_ROOT takes precedence if both set):

```
bin/cgl-cockpit examples/hello-lab
```

## What it shows

- **Header:** "Studio Cockpit — `<federation_root_basename>`"
- **Lab table (left):** one row per lab with:
  - Status symbol (`!`=needs_review, `●`=active, `◐`=idle, `○`=stale, `×`=error)
  - Lab ID, Kind
  - Current orientation objective (truncated to 50 chars)
  - Claw count
  - Promotion candidate count
- **Director Queue (right):** list of bundles whose `promotion_recommendation`
  requires review (`keep_evidence`, `promote`, `partial_promote`).
  Format: `<lab_id>: <bundle_id>: <recommendation>`.

## Keybindings

| Key   | Action                                           |
|-------|--------------------------------------------------|
| `q`   | Quit                                             |
| `r`   | Refresh data from disk                           |
| Enter | Show lab detail in notification + log            |

## Not yet implemented

- Navigation to a per-lab detail screen (no multi-screen routing yet)
- Promotion actions (`cgl-promote` is out of scope — display only)
- Chat/supervisor pane
- Color-coded status (functional symbol indicators used instead)
- Multi-lab federation walking (currently: root dir itself, or one-level subdirs)
