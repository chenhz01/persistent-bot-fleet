# Changelog

## v0.1.1 — 2026-10-11 (self-review revision, iteration 2)

### Improved (completeness/correctness dimension)
- Added an **oversized-message edge test** (MAX_TEXT+1) — v0.1.0 shipped the
  guard but never tested it; self-review against ALIGNMENT rule 13 flagged
  the untested guard. Test count 15 → 17.
- README: added the "concurrent writers" limitation to Limits (was only
  implied by the checksum paragraph) and a second-order effect (broadcast
  fan-out volume growth ~O(bots²)) that was missing entirely in v0.1.0.
- README FAQ expanded with the plaintext-state warning for secret payloads.

## v0.1.0 — 2026-10-11 (initial draft)

- `Fleet` runtime: spawn / send / broadcast / inbox / drain / roster.
- Checksummed single-file JSON state (SHA-256 over canonical body),
  atomic saves via temp-file + `os.replace`.
- Guards: unknown bots, duplicate names, self-messages, empty text,
  1 MB message cap, 1000-bot fleet cap.
- CLI: spawn / send / broadcast / inbox / list (argparse, `--state`).
- `self_test.py`: 15 tests, functional / error-path / extreme-edge
  (empty fleet, 200 KB message, 10k-message fan-in, garbage state file).
- README, LICENSE (MIT), initial alignment audit.
