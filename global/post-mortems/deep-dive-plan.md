# Deep-Dive Plan: Autonomous Build Failures

**Date:** 2026-05-02  
**Scope:** 87 autonomous sessions (2026-04-26 to 2026-05-02)  
**Trigger:** Cron job 88962226f2c3 (every 30m, 24 iterations)  
**Status:** Active deep-dive investigation

---

## 1. Executive Summary

The autonomous build loop ran 87 sessions over ~6 days. Only 9 produced findings. The remaining 78 sessions either produced nothing, hallucinated session IDs, wrote empty plans, or failed at the trial level with no actionable output. The dominant failure mode is **template variable non-resolution**: the agent passes literal `{{inputs.target}}` and `{{inputs.flags}}` placeholders into shell commands and filenames instead of resolving them first.

**Key Finding:** The agent is using the wrong template syntax. The tool cards use `{target}` (single braces), but the agent writes `{{inputs.target}}` (double braces). These are fundamentally different templates — single braces are Python format strings, double braces are Jinja2. If the dispatch system uses Python `.format()`, then `{target}` works but `{{inputs.target}}` becomes literal `{{inputs.target}}`.

---

## 2. Root Cause Analysis

### 2.1 Template Resolution (Critical)

**Evidence:**
- Session `01KQGKSK03QY35VDPJWDVX7K30`: Nmap artifact shows command `/usr/lib/nmap/nmap --privileged -oX - {{inputs.flags}} scanme.nmap.org`
- Session `01KQ59R4KY2W2555J0QQZXWFWY`: Wrote file `host_{{inputs.target}}.json` with payload `null`

**Root Cause:**
The agent's prompt/template engine does not resolve `{{inputs.*}}` placeholders before generating commands or filenames. The agent appears to treat these as literal strings.

**Why this happens:**
1. The tool cards use `{target}` syntax (single braces) for Python `.format()`
2. The agent writes `{{inputs.target}}` (double braces) because it sees this in the cron prompt
3. The dispatch system's `safe_expand()` function replaces `{target}` with the actual value, but if the agent writes `{{inputs.target}}`, it becomes a literal string because Python's `.format()` treats `{{` as an escaped `{`

**Fix:** Add validation in `dispatch.py` to reject inputs with `{{inputs.*}}` patterns and add explicit instructions to the agent in `HERMES.md` to resolve all templates before calling `invoke_skill`.

**Status:** Fixed in Phase 1 (see previous fix).

---

### 2.2 Empty Plans (High)

**Evidence:**
All 45 sessions that wrote a `plan.json` contain `"steps": []` — zero steps.

**Root Cause:**
The `plan` skill expects the agent to write a markdown plan in `.hermes/plans/`, but the agent is writing a JSON plan with empty steps. The agent is not following the skill's instructions correctly.

**Why this happens:**
1. The cron job uses the `plan` skill, but the skill is for writing markdown plans, not JSON plans
2. The agent doesn't understand how to create a proper plan
3. There's no validation step that checks plan quality before execution

**Fix:**
1. Update the cron job to use the correct skill for JSON plan generation
2. Add a plan validation step in the dispatch pipeline
3. Provide explicit instructions in the agent's prompt about how to generate plans

**Status:** Pending.

---

### 2.3 Missing STATUS.md (High)

**Evidence:**
The cron job's prompt instructs the agent to:
```
1. Read ~/.securatron/projects/lab-internal/STATUS.md to find current progress and what's next.
```

But `STATUS.md` does not exist.

**Root Cause:**
The STATUS.md file was never created. The cron job references it but it doesn't exist, so the agent has no context about what to work on.

**Why this happens:**
1. The file was never created during the initial setup
2. The agent doesn't know how to create it
3. There's no fallback mechanism if the file doesn't exist

**Fix:**
1. Create a STATUS.md file with the current state of the project
2. Update the cron job to handle the case where STATUS.md doesn't exist
3. Add instructions for the agent to maintain STATUS.md after each iteration

**Status:** Pending.

---

### 2.4 Hallucinated Session IDs (High)

**Evidence:**
- `sess_123` — 1 artifact file (64 bytes), clearly placeholder
- `sess_456` — 1 artifact file (61 bytes), clearly placeholder

**Root Cause:**
The agent is generating fake session IDs instead of using the actual session ID from the cron job context.

**Why this happens:**
1. The agent doesn't know how to generate a proper session ID
2. The agent is hallucinating session IDs because it doesn't have access to the ULID generation logic
3. There's no validation step that checks if the session ID is valid

**Fix:**
1. Update the cron job to pass the session ID to the agent
2. Add validation in the dispatch pipeline to check if the session ID is valid
3. Add instructions for the agent to use the actual session ID

**Status:** Pending.

---

### 2.5 Trial Classification (Medium)

**Evidence:**
- 22 trials failed with `FM-11` on `web.nikto` targeting `scanme.nmap.org`
- 11 trials failed with `FM-2` on `web.whatweb` targeting `scanme.nmap.org`
- Failure reason stored as `'result': 11` — the field name is wrong

**Root Cause:**
The trial runner is not using the parser's `ok`/`reason` fields to classify failures. Instead, it's falling through to a default "unknown" reason when the parser returns structured errors.

**Why this happens:**
1. The parser returns structured errors, but the trial runner doesn't handle them correctly
2. The `FM-2` and `FM-11` error codes are not being mapped to descriptive reasons
3. The trial ledger schema is not being followed correctly

**Fix:**
1. Update the trial runner to properly handle parser errors
2. Map error codes to descriptive reasons
3. Add validation to ensure the trial ledger schema is followed

**Status:** Pending.

---

### 2.6 Deduplication (Low)

**Evidence:**
- `scanme.nmap.org` scanned 20+ times across sessions
- Identical artifacts repeated with identical content
- No deduplication or progress tracking

**Root Cause:**
The autonomous build loop has no mechanism to track what has already been scanned. It doesn't check the ledger to see if a target has already been scanned.

**Why this happens:**
1. The cron job doesn't include deduplication logic
2. The agent doesn't check the ledger before starting a scan
3. There's no progress tracking mechanism

**Fix:**
1. Update the cron job to check the ledger before starting a scan
2. Add deduplication logic to the dispatch pipeline
3. Track what has been scanned in the ledger

**Status:** Pending.

---

## 3. Deep-Dive Investigation Plan

### Phase 1: Template Resolution (Priority 1) - ✅ COMPLETED

**Goal:** Fix the template resolution bug so the agent resolves `{{inputs.*}}` placeholders before generating commands.

**Actions:**
1. [x] Add validation in `dispatch.py` to reject inputs with `{{inputs.*}}` patterns
2. [x] Add validation in `gate.py` to check for unresolved templates before execution
3. [x] Update agent instructions in `HERMES.md` to prevent the hallucination
4. [ ] Test the fix with a sample trial
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- Template variables resolve correctly in at least 3 consecutive sessions
- No literal `{{inputs.*}}` strings appear in commands or filenames

---

### Phase 2: Plan Generation (Priority 2)

**Goal:** Fix the plan generation so the agent creates proper plans with steps.

**Actions:**
1. [ ] Update the cron job to use the correct skill for JSON plan generation
2. [ ] Add a plan validation step in the dispatch pipeline
3. [ ] Provide explicit instructions in the agent's prompt about how to generate plans
4. [ ] Test the fix with a sample session
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- Plans contain at least 2 steps per session
- Plans are consistent with the agent's actual work
- No empty plans appear

---

### Phase 3: STATUS.md Creation (Priority 3)

**Goal:** Create the STATUS.md file and update the cron job to handle its absence.

**Actions:**
1. [ ] Create a STATUS.md file with the current state of the project
2. [ ] Update the cron job to handle the case where STATUS.md doesn't exist
3. [ ] Add instructions for the agent to maintain STATUS.md after each iteration
4. [ ] Test the fix with a sample session
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- STATUS.md exists and is up-to-date
- The agent can read and follow STATUS.md
- STATUS.md is maintained after each iteration

---

### Phase 4: Session ID Generation (Priority 4)

**Goal:** Fix the session ID generation so the agent uses actual session IDs.

**Actions:**
1. [ ] Update the cron job to pass the session ID to the agent
2. [ ] Add validation in the dispatch pipeline to check if the session ID is valid
3. [ ] Add instructions for the agent to use the actual session ID
4. [ ] Test the fix with a sample session
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- No hallucinated session IDs appear
- Session IDs are valid ULIDs
- Sessions can be queried and audited

---

### Phase 5: Trial Classification (Priority 5)

**Goal:** Fix the trial classification so failures are properly categorized.

**Actions:**
1. [ ] Update the trial runner to properly handle parser errors
2. [ ] Map error codes to descriptive reasons
3. [ ] Add validation to ensure the trial ledger schema is followed
4. [ ] Test the fix with a sample trial
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- Trial failures have descriptive reasons (not "unknown")
- Error codes are mapped to descriptive reasons
- The trial ledger schema is followed correctly

---

### Phase 6: Deduplication (Priority 6)

**Goal:** Fix the deduplication so the agent doesn't scan the same target multiple times.

**Actions:**
1. [ ] Update the cron job to check the ledger before starting a scan
2. [ ] Add deduplication logic to the dispatch pipeline
3. [ ] Track what has been scanned in the ledger
4. [ ] Test the fix with a sample session
5. [ ] Monitor next 10 autonomous sessions to verify the fix

**Verification:**
- No duplicate scans appear
- The ledger tracks what has been scanned
- The agent checks the ledger before starting a scan

---

## 4. Fix Priority Order

1. **Template resolution** — Fixes 3+ sessions at once (✅ COMPLETED)
2. **Plan generation** — Enables all future debugging (Pending)
3. **STATUS.md creation** — Provides context for the agent (Pending)
4. **Session ID generation** — Prevents wasted sessions (Pending)
5. **Trial classification** — Makes failures actionable (Pending)
6. **Deduplication** — Optimizes resource usage (Pending)

---

## 5. Verification Criteria

A fix is verified when:
- Template variables resolve correctly in at least 3 consecutive sessions
- Plans contain at least 2 steps per session
- STATUS.md exists and is up-to-date
- No hallucinated session names appear
- Trial failures have descriptive reasons (not "unknown")
- No duplicate scans appear
- Sessions produce structured findings (not just raw artifacts)

---

## 6. Next Steps

1. Complete Phase 1 testing and monitoring
2. Start Phase 2 investigation
3. Create STATUS.md file
4. Update cron job prompt
5. Monitor next 10 autonomous sessions

---

*Generated by autonomous build post-mortem analysis, 2026-05-02*
