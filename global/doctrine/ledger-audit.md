# Ledger Audit Report

## Overview

**Date:** 2026-05-01
**Total trials scanned:** 121
**Total failures found:** 36
**Success rate:** 64.5% (78/121)
**Unknown status:** 7

## Per-Skill Breakdown

| Skill | Entries | Success | Failure | Unknown |
|-------|---------|---------|---------|---------|
| fs.read | 1 | 1 | 0 | 0 |
| infra | 1 | 0 | 0 | 1 |
| kali.nmap | 15 | 15 | 0 | 0 |
| mem.write_session | 10 | 10 | 0 | 0 |
| recon.host.full | 4 | 4 | 0 | 0 |
| recon.host | 10 | 10 | 0 | 0 |
| shell.run | 3 | 1 | 2 | 0 |
| web.gobuster | 8 | 8 | 0 | 0 |
| web.nikto | 45 | 16 | 23 | 6 |
| web.whatweb | 24 | 13 | 11 | 0 |

## Molecule Status

- **recon.host.full**: 4 trials, all successful, avg 59s duration, 5 steps per run
- Molecule field populated only on trials written after `dispatch.py` fix (2026-05-01)

## Failure Patterns

| Pattern | Count | Mode | Status |
|---------|-------|------|--------|
| web.nikto FM-11 | 22 | known_defect | IT-web.nikto-001 closed |
| web.nikto FM-2 | 5 | parser_mismatch | IT-web.nikto-002 closed |
| web.whatweb FM-2 | 11 | parser_mismatch | IT-web.whatweb-001 closed |
| shell.run FM-11 | 2 | known_defect | IT-shell.run-001 closed |

## Improvement Ledger

- **Total ITs:** 4 (all closed)
- **Open ITs:** 0
- **Closed with verification:** 4

## Known Issues

1. 7 entries have missing `status` field (legacy format)
2. 6 entries have missing `timestamp` field (legacy format)
3. 1 entry has missing `skill_id` field (legacy format)
4. Molecule field only populated on newer trial entries

## Notes

- The `recon.host.full` molecule trial is the first with proper molecule metadata in the ledger
- The analyzer correctly handles both old-format and new-format entries
- No new improvement tickets generated (all patterns already have closed ITs)
- The FP-loop (fp-loop.md) is the active development mechanism; SIL runs periodically via cron
