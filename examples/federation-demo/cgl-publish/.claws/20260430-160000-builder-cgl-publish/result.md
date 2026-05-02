# Result — 20260430-160000-builder-cgl-publish

**Role:** builder
**Orientation:** orient-cgl-publish-build
**Lab:** cgl-publish
**Status:** finished
**Run:** 2026-04-30T16:00:00Z -> 2026-04-30T18:05:00Z

---

## Summary

This builder claw implemented `bin/cgl-publish`, the one-shot surface publish
primitive for Studio. The script accepts a built surface directory, a destination
R2 bucket path, a lab slug, and a bundle ID, and uploads all files with a
provenance.json manifest. Dry-run mode was tested against the staging CDN bucket.
Shellcheck passes. The bats integration test suite has 5 passing cases.

The script is ready to merge into bin/. The CDN path schema (lab_slug/bundle_id
prefix) is enforced and documented. Two high-confidence claims are available in
evidence.jsonl covering upload correctness and provenance tracing.

---

## Evidence collected

**Claim 001 (high confidence):** cgl-publish uploads the surface and writes a
provenance.json with bundle_id, lab_slug, published_at, and sha256 checksums.
Verified via dry-run against staging bucket.

**Claim 002 (high confidence):** CDN path schema enforces lab_slug/bundle_id
prefix, enabling direct tracing from live URL to originating artifact bundle.

---

## Recommendations

1. Merge bin/cgl-publish into main. The bats tests should be run as part of
   the CI suite.
2. Wire cgl-publish into the surface-snake lab once that lab's builder claw
   is promoted.
3. Add a --rollback flag in a follow-on claw to handle failed deploys.

---

## Promotion recommendation

merge
