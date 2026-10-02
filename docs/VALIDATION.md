# Version 0.1.0 validation

Verified locally on Windows 11, Python 3.14.6, Chromium 153, October 2, 2026.

| Requirement | Evidence | Result |
| --- | --- | --- |
| Commit predictions before response; preserve saved records across restart | `tests/test_lab.py` with actual SQLite storage | Pass |
| Correct chance score and separate unknown/missing/withdrawal outcomes | Independent expected Brier value 2/3 and denominator assertions | Pass |
| Deterministic learning comparison with learning disabled | Seed replay and distinct trace/value assertions | Pass |
| Evidence chain modification and truncation detection | JSON edits, retained receipt, verification failure | Pass |
| Local session, host and origin boundaries | Unauthorized and cross-origin HTTP requests rejected | Pass |
| Exports and recoverable validation errors | Real HTTP round-trip and spreadsheet formula neutralization | Pass |
| Complete observation UI and agent inspection | Playwright browser workflow; six control rows; evidence download | Pass |
| Mobile home layout | 390-pixel viewport, no horizontal page overflow; screenshot inspected | Pass |
| Runnable distribution | Built executable serves bundled assets, creates demo, exports, runs simulation, quits, verifies exports | Pass |

Commands: `python -m unittest discover -s tests -v` (10 tests), `python tests/browser_check.py`, `python tests/package_check.py`, `node --check web/app.js`.

Scope limits: macOS/Linux source paths were inspected, not executed. The unsigned Windows package was tested on this computer, not a clean second machine. No new biological study or inferential statistical validation was performed. Integrity verification checks events against a receipt; it does not independently authenticate observations or a receipt rewritten together with an export. Saved observations cannot be revised in this version.
