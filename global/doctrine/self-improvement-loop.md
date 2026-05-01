# Doctrine: Self-Improvement Loop (SIL)

## Purpose

The Self-Improvement Loop is the mechanism by which the SecuraTron harness
learns from its own failures and amplifies its own successes. It closes the
feedback cycle between **observation** (what happened), **extraction** (why it
happened), **action** (what we change), and **verification** (confirming the
change works).

Without SIL, post-mortems are museum pieces — written once, read rarely. With
SIL, every failed trial teaches the next trial.

## Relationship to Other Doctrine

| Doctrine | Role |
|----------|------|
| `fp-loop.md` | Per-atom validation: decompose → execute → observe → gate → adapt |
| `self-improvement-loop.md` | Cross-atom learning: extract patterns, apply fixes, verify outcomes |
| `memory-rules.md` | Persistent knowledge: what SIL learns becomes indexed memory |
| `promotion-gate.md` | Quality assurance: SIL prevents defective atoms from being promoted |
| `outer-builder-wiring.md` | Construction: SIL informs how new atoms are authored |

**SIL operates at a higher level than the fp-loop.** The fp-loop ensures each
atom is built correctly. SIL ensures the harness itself becomes better at
building atoms over time.

## The Four Phases

### Phase 1 — Observe (Per-Trial)

Every atom trial triggers an observation. This is lightweight and automatic.

**What is recorded:**
- Trial result (success/failure)
- Exit code and stderr content
- Duration (for timeout detection)
- Whether artifact was created and is non-empty

**Failure classification:** Each failure is tagged with a failure mode from
the canonical taxonomy (Section III). This is done by `analyze_trials.py`
after the trial completes, not during execution (to keep the hot path fast).

**Hard Rule:** No trial is allowed to fail silently. Even if the failure is
classified as "known" (see Section V), it must be logged with a reference to
the originating improvement ticket.

### Phase 2 — Extract (Periodic)

The extraction phase scans the complete ledger corpus for patterns. This runs
either manually or via cron (recommended: every 2 hours during active build
sprints).

**What it does:**
1. Loads all trial ledgers from `global/ledger/`
2. Groups failures by skill_id, target, and failure mode
3. Cross-references with post-mortems and the improvement ledger
4. Identifies **recurring failures** (same skill+target failing 3+ times)
5. Identifies **new patterns** (failure mode not yet documented)
6. Produces a **pattern report** written to `global/ledger/improvements.jsonl`

**Output format:** See Section IV — Improvement Ledger Schema.

### Phase 3 — Act (On-Demand)

When the extraction phase identifies a pattern, an Improvement Ticket (IT-NNN)
is created. The operator (or autonomous agent) then decides how to act:

**Action types:**
- **Fix the atom card** (wrong template, missing flags, wrong parser)
- **Fix the dispatcher** (bug in dispatch.py, gate.py, or parsers.py)
- **Fix the scope** (scope.yaml missing a target that should be there)
- **Add a precondition** (new check that should block known-failure inputs)
- **Update a postcondition** (new validation that should catch more defects)
- **Update doctrine** (fp-loop or SIL itself needs revision)

**Hard Rule:** Every action must be traced to the originating IT ticket. No
changes are made without an IT reference.

### Phase 4 — Verify (After Every Act)

After applying a fix, the loop MUST verify it works. This is not optional.

**Verification steps:**
1. Identify the original failing trial(s) that triggered the IT
2. Re-run the atom with the same inputs
3. Confirm the trial now succeeds
4. Update the IT status to "closed" with verification evidence
5. If verification fails, reopen the IT and return to Phase 3

**Hard Rule:** A closed IT without verification evidence is a phantom fix —
indistinguishable from no fix at all.

## Failure Mode Taxonomy

Every failure is classified into exactly one mode. This taxonomy is the
foundation of pattern detection. If a failure doesn't fit, create a new mode
via RP.

| Code | Mode | Description | Example |
|------|------|-------------|---------|
| FM-1 | rate_limit | Target rejected rapid repeated requests | scanme.nmap.org blocking nikto |
| FM-2 | parser_mismatch | Output doesn't match any registered parser | whatweb returns JSON not in parsers.py |
| FM-3 | scope_violation | Target not in scope.yaml | external target used without adding to scope |
| FM-4 | template_error | Command template expands to invalid shell | missing `{target}` in inputs dict |
| FM-5 | timeout | Tool exceeded timeout_seconds | 60s limit reached for deep scan |
| FM-6 | missing_binary | CLI tool not installed on host | `nikto: command not found` |
| FM-7 | network_unreachable | Target not reachable (port closed, DNS fail) | Juice Shop container not running |
| FM-8 | artifact_missing | Exit code 0 but no artifact file created | nikto JSON written to wrong path |
| FM-9 | postcondition_fail | Artifact exists but content invalid | empty JSON array, no findings |
| FM-10 | internal_error | Bug in dispatch.py, gate.py, or ledger.py | KeyError, TypeError, ValueError |
| FM-11 | known_defect | Failure from a documented, accepted defect | TD-7: maxtime exit code = 0 |

**Hard Rule:** Every failure entry in the improvement ledger MUST have a
`failure_mode` matching one of these codes. Unknown modes are filed as RPs.

## Improvement Ledger Schema

The improvement ledger is a JSONL file parallel to the atom ledgers. Each entry
represents one learned pattern or applied fix.

```json
{
  "improvement_id": "IT-web.nikto-001",
  "ts": "2026-04-27T10:00:00.000000Z",
  "phase": "observe|extract|act|verify",
  "skill_id": "web.nikto",
  "failure_mode": "rate_limit",
  "trigger_trial_ids": ["01KQ5YWR4JZZN77TF6RMN1HK20"],
  "description": "nikto returns empty output on scanme.nmap.org due to rate limiting",
  "root_cause": "Qualys Security Research group rate-limits rapid nikto requests",
  "action_taken": "none",
  "files_modified": [],
  "verification_status": "pending|passed|failed",
  "verification_evidence": null,
  "status": "open|closed|deferred|rejected",
  "related_post_mortem": "web.nikto.md",
  "related_defects": ["TD-3"]
}
```

**Phase semantics:**
- `observe`: A single failure was detected and classified
- `extract`: Pattern identified (same failure on 3+ trials)
- `act`: Fix was applied, files modified listed
- `verify`: Fix verified, evidence recorded

## Anti-Patterns (Never Do These)

- **Phantom fixes:** Closing an IT without re-running the failing trial
- **Silent failures:** Ignoring a failure because "it's expected" without
  logging it to the improvement ledger
- **Stale post-mortems:** Writing a post-mortem that isn't cross-referenced
  in the improvement ledger or memory index
- **Fix-forwarding:** Applying a workaround in the atom card without filing
  the originating IT ticket
- **Pattern blindness:** Ignoring a recurring failure because it's on a
  non-critical target (scanme.nmap.org rate limiting affects all web scanners)
- **Orphaned tickets:** Creating IT tickets that are never acted on or closed
  (all open ITs are reviewed every sprint)

## Sprint Review Protocol

At the end of each build sprint (or before cron job iteration N is complete):

1. **Review all open IT tickets** — close verified ones, defer or reject
   stale ones, escalate critical ones to the operator
2. **Audit the failure taxonomy** — are FM-1 through FM-11 sufficient? File
   RPs for new modes.
3. **Verify postcondition coverage** — run `analyze_trials.py` and confirm
   every failure has a classification
4. **Update scope.yaml if needed** — targets that consistently fail due to
   being out of scope should either be added to scope or the atom card
   should have a better error message

## Operational Procedures

### Running the Full Loop (Manual)

```bash
# Step 1: Scan ledgers and extract patterns
python3 ~/.securatron/global/bin/analyze_trials.py

# Step 2: Review detected patterns
python3 ~/.securatron/global/bin/apply_improvements.py list --open

# Step 3: View details of a specific ticket
python3 ~/.securatron/global/bin/apply_improvements.py view IT-web.nikto-001

# Step 4: Verify an improvement ticket
python3 ~/.securatron/global/bin/apply_improvements.py verify IT-web.nikto-001 --trial 01KQ5YWR4JZZN77TF6RMN1HK20

# Step 5: Close a verified ticket
python3 ~/.securatron/global/bin/apply_improvements.py close IT-web.nikto-001 --evidence "re-run on scanme.nmap.org succeeded, 3 consecutive passes"
```

### Automated Extraction (Cron)

```bash
# Run every 30 minutes during build sprints
* * 9-21 * * * cd ~/.securatron/global && python3 bin/analyze_trials.py --json >> global/ledger/extraction.log 2>&1

# Daily summary at 22:00
0 22 * * * python3 ~/.securatron/global/bin/apply_improvements.py list >> ~/.hermes/logs/sil-daily.txt 2>&1
```

### Quick Reference: Failure Mode Codes

| FM | Meaning | Typical Fix |
|----|---------|-------------|
| FM-1 | rate_limit | Add delay, rotate targets |
| FM-2 | parser_mismatch | Update atom parser in tools/*.yaml |
| FM-3 | scope_violation | Add target to scope.yaml or atom card |
| FM-4 | template_error | Fix command template or inputs dict |
| FM-5 | timeout | Increase timeout_seconds, optimize query |
| FM-6 | missing_binary | Install CLI tool |
| FM-7 | network_unreachable | Verify target availability |
| FM-8 | artifact_missing | Fix artifact path in template |
| FM-9 | postcondition_fail | Update postcondition validation |
| FM-10 | internal_error | Fix dispatch.py/gate.py bug |
| FM-11 | known_defect | Update defect tracker or fix root cause |

## Acceptance Criteria

- [x] Every failed trial appears in the improvement ledger with a failure mode
- [ ] Every open IT ticket has a root cause, action plan, and timeline
- [ ] Closed IT tickets have verification evidence (re-run results)
- [ ] No post-mortem is written without a corresponding improvement ledger entry
- [ ] The memory.index includes failure patterns from post-mortems (via reindex.py)
- [ ] The fp-loop references SIL: adapt step (Step 5) consults the improvement ledger
- [x] `analyze_trials.py` runs successfully against all current ledgers
- [ ] Gate.py postcondition evaluation is no longer a TODO stub

## Revision Proposals

### RP-SIL-001: Semantic Failure Detection (deferred)
**Proposed by:** hermes (uncertainty)
**Date:** 2026-04-29
**Section affected:** II, IV
**Problem:** Current failure mode taxonomy requires manual classification.
**Proposed change:** Add ML-based failure classification using sentence
transformers on stderr content.
**Justification:** Would reduce classification errors and enable natural
language queries against the failure corpus.
**Status:** deferred — FM-1 through FM-11 cover current needs.

### RP-SIL-002: Cross-Atom Correlation (pending)
**Proposed by:** hermes (uncertainty)
**Date:** 2026-04-29
**Section affected:** III, IV
**Problem:** Rate limiting on scanme.nmap.org affects ALL web scanners
(nikto, whatweb, gobuster) but is tracked as separate ITs per atom.
**Proposed change:** Add a "shared_defect" field to IT entries that links
atoms affected by the same root cause.
**Justification:** Enables group-fixing: one fix for scanme.nmap.org applies
to all web scanner atoms.
**Status:** pending — operator decision needed on cross-atom defect linking.

### RP-SIL-003: Automated Remediation Pipeline (pending)
**Proposed by:** hermes (uncertainty)
**Date:** 2026-04-29
**Section affected:** II, V
**Problem:** Phase 3 (Act) requires human intervention for every fix.
**Proposed change:** Define a set of "auto-remediable" patterns (e.g., FM-4
template errors with known fixes) that the loop can apply automatically.
**Justification:** Reduces operator fatigue for simple, well-understood fixes.
**Status:** pending — requires careful safety analysis before implementation.

## End of Doctrine v0.1
