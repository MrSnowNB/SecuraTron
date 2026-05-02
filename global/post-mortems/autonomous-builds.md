# Post-Mortem: Autonomous Build Failures

**Date**: 2026-05-02
**Scope**: 87 autonomous sessions (2026-04-26 to 2026-05-02)
**Trigger**: Cron job 88962226f2c3 (every 30m, 24 iterations)
**Status**: Deep-dive analysis in progress

---

## 1. Executive Summary

The autonomous build loop ran 87 sessions over ~6 days. Only 9 produced findings. The remaining 78 sessions either produced nothing, hallucinated session IDs, wrote empty plans, or failed at the trial level with no actionable output. The dominant failure mode is **template variable non-resolution**: the agent passes literal `{{inputs.target}}` and `{{inputs.flags}}` placeholders into shell commands and filenames instead of resolving them first.

---

## 2. Quantitative Overview

| Metric | Value |
|--------|-------|
| Total sessions | 87 |
| Sessions with findings | 9 (10%) |
| Sessions with artifacts | 83 (95%) — mostly empty/raw |
| Sessions with plans | 45 (52%) — all empty (steps: []) |
| Empty sessions (0 bytes) | 1 |
| Hallucinated session names | 2 (sess_123, sess_456) |
| Total trials recorded | 84 |
| Successful trials | 50 (60%) |
| Failed trials | 34 (40%) |

### Trial Success Rate by Tool

| Tool | Trials | Success | Failure | Rate |
|------|--------|---------|---------|------|
| web.nikto | 45 | 22 | 23 | 49% |
| web.whatweb | 24 | 13 | 11 | 54% |
| kali.nmap | 15 | 15 | 0 | 100% |

---

## 3. Error Categories (Ranked by Severity)

### 3.1 CRITICAL: Template Variable Non-Resolution

**Evidence:**
- Session `01KQGKSK03QY35VDPJWDVX7K30`: Nmap artifact shows command `/usr/lib/nmap/nmap --privileged -oX - {{inputs.flags}} scanme.nmap.org`
  - Nmap stderr: `Failed to resolve "{{inputs.flags}}"` — treated it as a hostname
- Session `01KQ59R4KY2W2555J0QQZXWFWY`: Wrote file `host_{{inputs.target}}.json` with payload `null`
  - Agent wrote literal template string as filename instead of `host_scanme.nmap.org.json`

**Root Cause:**
The agent's prompt/template engine does not resolve `{{inputs.*}}` placeholders before generating commands or filenames. The agent appears to treat these as literal strings.

**Impact:** Every session that relied on dynamic input resolution produced broken output.

### 3.2 HIGH: Empty Plans Everywhere

**Evidence:**
All 45 sessions that wrote a `plan.json` contain `"steps": []` — zero steps.

**Impact:** No structured planning occurs. The agent executes raw without a plan, making debugging impossible and producing repetitive, undirected work.

### 3.3 HIGH: Hallucinated Session IDs

**Evidence:**
- `sess_123` — 1 artifact file (64 bytes), clearly placeholder
- `sess_456` — 1 artifact file (61 bytes), clearly placeholder

**Impact:** These sessions have no real identity in the session lifecycle. They can't be queried, audited, or tracked.

### 3.4 MEDIUM: Nikto Empty Artifact Files

**Evidence:**
- Many `nikto-*.json` files are 0 bytes (empty)
- The nikto parser (`parse_nikto_scan` in `parsers.py`) correctly handles this case and returns `"error": "nikto_no_artifact"`
- But 16 failures have reason `"unknown"` — meaning the trial runner can't classify them

**Root Cause:** Nikto `-maxtime 30s` combined with `-Format json -output file` creates the JSON file even when the scan fails. The file is empty. The parser detects this, but the trial ledger shows "unknown" reason, suggesting the trial runner isn't using the parser result correctly.

### 3.5 MEDIUM: WhatWeb Parser Fragility

**Evidence:**
- 11 failures on scanme.nmap.org (46% failure rate)
- Failure reason stored as `'result': 11` — the field name is wrong
- Parser uses `re.search(r"(\[.*\])")` to extract JSON array from stdout

**Root Cause:** WhatWeb `--log-json /dev/stdout` may produce non-JSON output on errors. The regex may match non-JSON content, causing `json.loads()` to fail.

### 3.6 LOW: Duplicate Work

**Evidence:**
- scanme.nmap.org scanned 20+ times across sessions
- Identical artifacts repeated with identical content
- No deduplication or progress tracking

**Impact:** Wasted compute cycles and trial quota on already-scanned targets.

---

## 4. Deep-Dive Analysis Plan

### Phase 1: Template Resolution (Priority 1)

**Questions to answer:**
1. Where does the agent receive template variables? Is it from the cron prompt, the skill prompt, or the plan.json?
2. Does the dispatch system handle `{{inputs.*}}` resolution? Or does it expect the agent to do it?
3. Is the agent's prompt explicitly told to resolve templates, or is this assumed?

**Action items:**
- [ ] Read the cron job prompt (job 88962226f2c3) to see how it passes inputs
- [ ] Read the `plan` skill to see if template resolution is documented
- [ ] Check if dispatch.py has any template interpolation logic
- [ ] Verify: the template syntax should be `{target}` (curly braces) or `{{inputs.target}}` (double braces)? The tool cards use `{target}` but the agent writes `{{inputs.target}}`

### Phase 2: Plan Quality (Priority 2)

**Questions to answer:**
1. Why are all plans empty? Is the agent not generating steps, or is it generating steps but writing an empty array?
2. What does the `plan.json` format actually expect?
3. Is there a validation step that checks plan quality?

**Action items:**
- [ ] Read the `plan` skill to understand the expected plan format
- [ ] Compare the plan card schema with what the agent writes
- [ ] Check if there's a "plan gate" that validates steps exist before execution

### Phase 3: Trial Failure Classification (Priority 3)

**Questions to answer:**
1. Why do nikto failures show `"unknown"` reason instead of `"nikto_no_artifact"`?
2. Why do whatweb failures show `'result': 11` as the reason?
3. Is the trial runner using the parser's `ok`/`reason` fields correctly?

**Action items:**
- [ ] Trace a specific nikto failure through the dispatch pipeline
- [ ] Check the `run_trials_nikto.cpython-313.pyc` (compile from source) or read `dispatch.py`
- [ ] Verify that parser errors are properly classified

### Phase 4: Session Lifecycle (Priority 4)

**Questions to answer:**
1. How are session IDs generated? Why does the agent produce `sess_123`?
2. What causes a session to be completely empty (0 bytes)?
3. Is there a session creation validation?

**Action items:**
- [ ] Read the session lifecycle doctrine (`~/.securatron/global/doctrine/session-lifecycle.md`)
- [ ] Check how the cron job triggers new sessions
- [ ] Verify the ULID generation is deterministic

---

## 5. Root Cause Hypotheses

### Hypothesis 1: Template Syntax Mismatch
The tool cards use `{target}` syntax (single braces). The agent writes `{{inputs.target}}` (double braces). These are different templates — single braces are Python format strings, double braces are Jinja2. If the dispatch system uses Python `.format()`, then `{target}` works but `{{inputs.target}}` becomes literal `{{inputs.target}}`.

**Test:** Check if the tool card `{target}` gets resolved by the dispatch system before reaching the agent.

### Hypothesis 2: Agent Prompt Missing Template Instructions
The agent's cron prompt may not explicitly instruct it to resolve template variables. The agent assumes it should write `{{inputs.target}}` literally because that's what it sees in the tool card.

**Test:** Add explicit template resolution instructions to the cron prompt.

### Hypothesis 3: Dispatch System Bug
The trial runner may not be using the parser's `ok`/`reason` fields to classify failures. Instead, it may be falling through to a default "unknown" reason when the parser returns structured errors.

**Test:** Trace `web.nikto` failure `01KQG70NBAFW5WZCSH8SAJAW76` through the full pipeline.

---

## 6. Fix Priority Order

1. **Template resolution** — Fixes 3+ sessions at once
2. **Plan generation** — Enables all future debugging
3. **Trial classification** — Makes failures actionable
4. **Session lifecycle** — Prevents wasted sessions
5. **Deduplication** — Optimizes resource usage

---

## 7. Verification Criteria

A fix is verified when:
- Template variables resolve correctly in at least 3 consecutive sessions
- Plans contain at least 2 steps per session
- Trial failures have descriptive reasons (not "unknown")
- No hallucinated session names appear
- Sessions produce structured findings (not just raw artifacts)

---

*Generated by autonomous build post-mortem analysis, 2026-05-02*
