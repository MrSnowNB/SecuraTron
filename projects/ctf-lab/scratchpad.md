# AUDIT RUNNER HARDENING REPORT

**Date:** 2026-05-14T01:45:00Z
**Operator:** Mark

## EXECUTIVE SUMMARY

Three critical flaws were patched in the audit runner CI/CD engine. All 21 tests pass post-patch. A fourth issue (condition evaluation) was identified but deferred.

---

## PATCH 1: False Positive Fix (Default True -> False)

**File:** `~/.securatron/global/bin/audit_runner.py` (lines 153-154)
**Change:** `json_output.get("ok", True)` -> `json_output.get("ok", False)`

**Impact:** Tools that don't return an `ok` field now FAIL instead of PASS.
**Verification:** All 21 tools DO return `ok` fields, so no failures observed. The fix is correctly applied and defensive — any future tool that omits `ok` will fail the audit.

---

## PATCH 2: State Bleed Fix (Session Isolation)

**File:** `~/.securatron/global/bin/audit_runner.py` (line 71)
**Change:** `"TEST"` -> `f"TEST-{tool_id}-{_ts}"`

**Impact:** Each test gets a unique session ID (e.g., `TEST-kali.nmap-1778721600`), preventing `.state/` data from one tool polluting another.
**Verification:** Confirmed unique session IDs in dispatch calls.

---

## PATCH 3: Blast Radius Fix (Safe Targets)

**File:** `~/.securatron/global/bin/audit_runner.py` (line 26)
**Change:** `_SAFETNET = "192.0.2.1"` -> `_SAFETNET = "127.0.0.1"`

**Reasoning:** 192.0.2.1 causes TCP SYN connections to HANG (kernel SYN timeout, no RST). 127.0.0.1 (localhost) fails fast — connections are immediately refused or accepted.

**Additional fix:** `~/.securatron/global/tools/auth.hydra.yaml`:
- Added `default: 65534` for `port` input
- Added `default: http-head` for `service` input (was missing, caused empty-string command)
- Added `{port}` to command template: `http-head://{target}:{port}`

**Why 127.0.0.1?** The audit runner tests TOOL FUNCTIONALITY, not TARGET exploitation. Localhost is safe because:
- No external network access
- Tools report what they find (no blast radius)
- Destructive tools operate on isolated session paths

---

## PATCH 4: Auth.hydra Default Inputs

**File:** `~/.securatron/global/tools/auth.hydra.yaml`

The atom card was missing defaults for `service` and `port` inputs. Without defaults:
- `service` became empty string: `hydra -L ... -P ... ://127.0.0.1 ...` (invalid URI)
- The command template didn't include `{port}`, always using default port

**Fix:** Added `default: 65534` (port) and `default: http-head` (service). Port 65534 has no service, so hydra fails fast with clear error.

---

## IDENTIFIED DEFERRED ISSUE: Condition Evaluation Bug

**Location:** `~/.securatron/global/bin/dispatch.py` — `_evaluate_condition()` (line 366)

**Bug:** When a condition string lacks `{{...}}` template markers (e.g., `'steps.network_scan.result.ports contains 80 or 443'`), `eval()` fails with `NameError` (because `steps` is not defined). The except clause falls back to `bool(resolved_condition)`, which is **always True** for non-empty strings.

**Impact:** All condition-gated molecule steps run regardless of whether the condition is met. This means:
- Steps like `browser_recon` run even when port 80/443 is closed
- Molecules process unnecessary work and may fail on unexpected steps
- Condition gates are effectively no-ops

**Severity:** Medium (does not cause false positives in audit, but causes incorrect molecule behavior)

**Fix needed:** Resolve `steps.X.result.Y` references in condition strings BEFORE eval, similar to how `_resolve_condition` works for template-based conditions.

---

## FINAL AUDIT RESULTS

```
[AUDIT] Complete: 21 passed, 0 failed, 21 total

Atoms (12): auth.hydra, exploit.db.search, fs.read, kali.nmap, mem.read,
            mem.write_session, shell.run, system.tool.test, web.browser.inspect,
            web.gobuster, web.nikto, web.whatweb
Molecules (9): auth.network.spray, ctf.full.pwn, ctf.priv_esc, ctf.recon.full,
               ctf.web.assault, recon.host.full, recon.host, system.audit.suite,
               web.recon.explore
```

**Report:** `~/.securatron/global/evidence/locker/AUDIT_REPORT_20260514_013221.md`
**Evidence dir:** `~/.securatron/global/evidence/locker` (763 files)

---

## TOOLS MODIFIED

1. `~/.securatron/global/bin/audit_runner.py` — 3 patches
2. `~/.securatron/global/tools/auth.hydra.yaml` — 3 additions (port default, service default, port injection)

## NO CHANGES TO

- `~/.securatron/global/bin/dispatch.py` (condition bug identified but not fixed)
- `~/.securatron/global/tools/*.yaml` (except auth.hydra)
- `~/.securatron/global/skills/*.yaml` (molecule cards unchanged)
