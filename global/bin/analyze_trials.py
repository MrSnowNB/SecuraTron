#!/usr/bin/env python3
"""analyze_trials.py — Self-Improvement Loop Phase 2: Extract

Scans all atom trial ledgers, classifies failures, cross-references with
post-mortems, and produces improvement ledger entries for recurring patterns.

Usage:
    python3 analyze_trials.py [--json] [--dry-run]

Output:
    - Prints a summary of findings to stdout
    - Writes new entries to global/ledger/improvements.jsonl
    - Returns exit code 0 on success, 1 on critical issues

Failure Mode Taxonomy (FM-1 through FM-11):
    FM-1:  rate_limit          - Target rejected rapid repeated requests
    FM-2:  parser_mismatch     - Output doesn't match registered parser
    FM-3:  scope_violation     - Target not in scope.yaml
    FM-4:  template_error      - Command template expands to invalid shell
    FM-5:  timeout             - Tool exceeded timeout_seconds
    FM-6:  missing_binary      - CLI tool not installed
    FM-7:  network_unreachable - Target not reachable
    FM-8:  artifact_missing    - Exit code 0 but no artifact created
    FM-9:  postcondition_fail  - Artifact exists but content invalid
    FM-10: internal_error      - Bug in dispatch.py, gate.py, or ledger.py
    FM-11: known_defect        - Failure from documented, accepted defect
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path.home() / ".securatron"
LEDGER_DIR = BASE_DIR / "global" / "ledger"
IMPROVEMENT_LEDGER = BASE_DIR / "global" / "ledger" / "improvements.jsonl"
POST_MORTEM_DIR = BASE_DIR / "global" / "post-mortems"
INDEX_DB = BASE_DIR / "global" / "memory" / "index.db"


# ============================================================
# Failure Mode Classification
# ============================================================

def classify_failure(exit_code, stderr, stdout, reason, result, duration_ms, timeout_seconds):
    """Classify a failure into a canonical failure mode (FM-1 through FM-11).

    The reason field comes from the ledger entry and may contain error
    descriptions. Status comes from the 'status' field.
    """
    reason_str = str(reason) if reason else ""

    # Molecule step failure
    if reason_str == "step_failed":
        return "FM-10"

    # Known structured error reasons from parsers
    if reason_str == "nikto_no_artifact":
        return "FM-8" # artifact_missing — tool ran but produced no output
    if reason_str == "parsing_exception":
        return "FM-2" # parser_mismatch

    # Timeout
    if reason == "timeout_exceeded" or (duration_ms and duration_ms >= (timeout_seconds or 60) * 1000 * 0.9):
        return "FM-5"
    if re.search(r'timeout|exceeded|maxtime|time limit', reason_str + stderr, re.IGNORECASE):
        return "FM-5"

    # Missing binary
    if re.search(r'command not found|no such file|cannot find|not found', stderr, re.IGNORECASE):
        return "FM-6"

    # Scope violation indicators
    if re.search(r'scope|out of scope|unauthorized|forbidden', stderr, re.IGNORECASE):
        return "FM-3"

    # Network unreachable
    if re.search(r'connection refused|connection timed out|no route to host|name resolution', stderr, re.IGNORECASE):
        return "FM-7"

    # Rate limiting
    if re.search(r'rate.?limit|too many requests|throttl|bandwidth|qualys', stderr, re.IGNORECASE):
        return "FM-1"
    if re.search(r'reset|rejected|refused', stderr, re.IGNORECASE) and exit_code != 0:
        return "FM-1"

    # Parser mismatch (KeyError on 'result' — dispatch can't extract JSON)
    if reason_str == "'result'" or 'KeyError' in reason_str or (reason is None and exit_code != 0):
        return "FM-2"

    # Internal errors (dispatch.py bugs)
    if reason and any(x in reason_str for x in ['KeyError', 'TypeError', 'ValueError', 'AttributeError']):
        return "FM-10"
    if 'dispatch' in reason_str.lower():
        return "FM-10"

    # Artifact missing (exit code 0 but empty/no artifact)
    if exit_code == 0 and (not stdout or len(stdout.strip()) == 0):
        return "FM-8"

    # Template error
    if re.search(r'unrecognised.*format|invalid.*parameter|missing.*argument|usage:', stderr, re.IGNORECASE):
        return "FM-4"

    # Postcondition fail (exit 0 but suspicious stderr)
    if exit_code == 0 and stderr:
        stderr_lower = stderr.lower()
        if 'error' in stderr_lower and 'maxtime' not in stderr_lower:
            return "FM-9"

    # Default: unclassified failure (status=failure with no clear cause)
    return "FM-11"  # known_defect or unclassified


def load_post_mortems():
    """Load all post-mortems and extract known defect IDs and gotcha keywords."""
    pms = {}
    if not POST_MORTEM_DIR.exists():
        return pms

    for pm_file in POST_MORTEM_DIR.glob("*.md"):
        pm_id = pm_file.stem
        text = pm_file.read_text()
        pms[pm_id] = {
            "text": text,
            "defects": re.findall(r'TD-(\d+)', text),
            "keywords": re.findall(r'\b[A-Z]{2,}\b', text),
        }
    return pms


def load_improvement_ledger():
    """Load existing improvement ledger entries."""
    entries = []
    if IMPROVEMENT_LEDGER.exists():
        with open(IMPROVEMENT_LEDGER) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return entries


def load_all_trials():
    """Load all trial entries from all ledger files."""
    all_trials = []
    if not LEDGER_DIR.exists():
        return all_trials

    for ledger_file in sorted(LEDGER_DIR.glob("*.trials.jsonl")):
        skill_id = ledger_file.stem.replace(".trials", "")
        if skill_id == "improvements":
            continue
        with open(ledger_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        entry["_source_ledger"] = skill_id
                        all_trials.append(entry)
                    except json.JSONDecodeError:
                        continue
    return all_trials


def load_atom_cards():
    """Load all atom and molecule cards for timeout_seconds context."""
    cards = {}
    # Load from tools/ directory
    tools_dir = BASE_DIR / "global" / "tools"
    if tools_dir.exists():
        import yaml
        for card_file in tools_dir.glob("*.yaml"):
            try:
                with open(card_file) as f:
                    card = yaml.safe_load(f)
                    cards[card.get("id")] = card
            except Exception:
                continue
    # Load from skills/ directory (molecules)
    skills_dir = BASE_DIR / "global" / "skills"
    if skills_dir.exists():
        import yaml
        for card_file in skills_dir.glob("*.yaml"):
            try:
                with open(card_file) as f:
                    card = yaml.safe_load(f)
                    cards[card.get("id")] = card
            except Exception:
                continue
    return cards


def load_scope():
    """Load project scope for reference."""
    import yaml
    scope_file = BASE_DIR / "projects" / "lab-internal" / "scope.yaml"
    if scope_file.exists():
        with open(scope_file) as f:
            return yaml.safe_load(f)
    return {}


def detect_patterns(trials, pms, cards):
    """Detect recurring failure patterns across trials."""
    failure_groups = defaultdict(list)
    molecule_failures = defaultdict(list)  # molecule-level tracking

    for trial in trials:
        status = trial.get("status", "unknown")
        if status == "success":
            continue

        skill_id = trial.get("skill_id", trial.get("_source_ledger", "unknown"))
        reason = trial.get("reason", "") or trial.get("result", "")[:200] if isinstance(trial.get("result"), str) else ""
        stderr = reason
        stdout = ""
        duration_ms = trial.get("duration_ms")
        timeout_seconds = (cards.get(skill_id, {})
                           .get("execution", {})
                           .get("timeout_seconds", 60))

        fm = classify_failure(-1, stderr, stdout, reason, None, duration_ms, timeout_seconds)
        failure_groups[(skill_id, fm)].append({
            "trial_id": trial.get("trial_id", trial.get("ulid", "unknown")),
            "target": trial.get("target", "unknown"),
            "stderr_preview": stderr[:200] if stderr else "",
            "reason": str(reason) if reason else "",
            "timestamp": trial.get("ts", trial.get("timestamp", "")),
            "steps": trial.get("steps", []),
        })

        # Track molecule-level failures separately
        if trial.get("molecule") and status == "failure":
            molecule_failures[(trial.get("molecule"), skill_id)].append(trial)

    # Identify recurring patterns (2+ failures of same mode for same skill)
    patterns = {}
    for (skill_id, fm), failures in failure_groups.items():
        if len(failures) >= 2:
            patterns[(skill_id, fm)] = failures

    return patterns, molecule_failures


def generate_improvement_entries(patterns, trials, pms, improvement_entries):
    """Generate improvement ledger entries for detected patterns."""
    new_entries = []

    # Build set of existing IT IDs from current improvement ledger
    existing_its = set(e.get("improvement_id", "") for e in improvement_entries)

    # Count current max IT number per skill
    it_counters = defaultdict(int)
    for entry in improvement_entries:
        iid = entry.get("improvement_id", "")
        m = re.match(r'IT-([^.]+)\.(\d+)', iid)
        if m:
            skill = m.group(1)
            num = int(m.group(2))
            it_counters[skill] = max(it_counters[skill], num)

    # Process each pattern
    for (skill_id, fm), failures in patterns.items():
        # Determine if we already have an open IT for this pattern
        existing_it = None
        for e in improvement_entries:
            if (e.get("skill_id") == skill_id and
                e.get("failure_mode") == fm and
                e.get("status") == "open"):
                existing_it = e
                break

        if existing_it:
            # Append trigger trial IDs to existing IT
            new_trial_ids = [f["trial_id"] for f in failures if f["trial_id"] not in existing_it.get("trigger_trial_ids", [])]
            if new_trial_ids:
                updated = dict(existing_it)
                updated["trigger_trial_ids"] = existing_it.get("trigger_trial_ids", []) + new_trial_ids
                updated["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                updated["phase"] = "extract"
                new_entries.append(updated)
            continue

        # Check if this pattern was already closed/verified — skip
        for e in improvement_entries:
            if (e.get("skill_id") == skill_id and
                e.get("failure_mode") == fm and
                e.get("status") == "closed" and
                e.get("verification_status") == "passed"):
                # Already fixed — don't recreate
                break
        else:
            # Create new IT
            it_counters[skill_id] += 1
            it_id = f"IT-{skill_id}-{it_counters[skill_id]:03d}"

            # Check if this matches a known defect from post-mortems
            related_defects = []
            related_pm = None
            for pm_id, pm_data in pms.items():
                if pm_id == skill_id:
                    related_pm = pm_id
                    related_defects = pm_data["defects"]

            # Build description from failure evidence
            sample = failures[0]
            description = f"{len(failures)} trials failed with {fm} on {skill_id}"
            if sample.get("target") and sample["target"] != "unknown":
                description += f" targeting {sample['target']}"

            # Determine root cause from evidence
            root_cause = "insufficient evidence"
            if sample.get("stderr_preview"):
                root_cause = sample["stderr_preview"][:300]
            if sample.get("reason"):
                root_cause = sample["reason"]

            entry = {
                "improvement_id": it_id,
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "phase": "extract",
                "skill_id": skill_id,
                "failure_mode": fm,
                "trigger_trial_ids": [f["trial_id"] for f in failures],
                "description": description,
                "root_cause": root_cause,
                "action_taken": "none",
                "files_modified": [],
                "verification_status": "pending",
                "verification_evidence": None,
                "status": "open",
                "related_post_mortem": related_pm,
                "related_defects": related_defects,
            }
            new_entries.append(entry)

    return new_entries


def print_summary(patterns, new_entries, all_trials, molecule_failures=None):
    """Print a human-readable summary of findings."""
    total_trials = len(all_trials)
    total_failures = sum(1 for t in all_trials if t.get("status") not in ("success",))
    total_patterns = len(patterns)
    total_new_its = len(new_entries)

    print("=" * 60)
    print("Self-Improvement Loop — Phase 2: Extract")
    print("=" * 60)
    print(f"  Total trials scanned:   {total_trials}")
    print(f"  Total failures found:   {total_failures}")
    print(f"  Recurring patterns:     {total_patterns}")
    print(f"  New improvement tickets: {total_new_its}")

    # Molecule-level summary
    if molecule_failures:
        total_molecules = len(molecule_failures)
        print(f"  Molecules with failures: {total_molecules}")
        if total_molecules > 0:
            print()
            print("MOLECULE FAILURES:")
            print("-" * 60)
            for (mol_id, skill_id), trials_list in sorted(molecule_failures.items()):
                steps = trials_list[0].get("steps", []) if trials_list else []
                step_summary = []
                for s in steps:
                    st = s.get("status", "unknown")
                    step_summary.append(f"{s.get('id', '?')}={st}")
                print(f"  {mol_id} (via {skill_id}): {len(trials_list)} failures")
                print(f"    Steps: {', '.join(step_summary)}")
    print()

    if patterns:
        print("PATTERNS DETECTED:")
        print("-" * 60)
        for (skill_id, fm), failures in sorted(patterns.items()):
            print(f"  [{fm}] {skill_id}: {len(failures)} failures")
            for f in failures[:3]:  # show first 3
                print(f"    - trial {f['trial_id'][:12]}... target={f['target']}")
            if len(failures) > 3:
                print(f"    ... and {len(failures) - 3} more")
        print()

    if new_entries:
        print("NEW IMPROVEMENT TICKETS:")
        print("-" * 60)
        for entry in new_entries:
            print(f"  {entry['improvement_id']}: {entry['description']}")
        print()

    print("=" * 60)
    if total_failures == 0:
        print("STATUS: All trials successful — no improvements needed.")
    else:
        print(f"STATUS: {total_failures} failures found, {total_new_its} new ITs created.")
    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze trial ledgers for self-improvement patterns")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of human-readable")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to improvement ledger")
    args = parser.parse_args()

    # Load data
    trials = load_all_trials()
    pms = load_post_mortems()
    cards = load_atom_cards()
    improvement_entries = load_improvement_ledger()

    # Detect patterns
    patterns, molecule_failures = detect_patterns(trials, pms, cards)

    # Generate new improvement entries
    new_entries = generate_improvement_entries(patterns, trials, pms, improvement_entries)

    # Print summary
    if args.json:
        print(json.dumps({
            "total_trials": len(trials),
            "patterns": {f"{k[0]}.{k[1]}": v for k, v in patterns.items()},
            "molecule_failures": {f"{k[0]}.{k[1]}": [t.get("trial_id") for t in v] for k, v in molecule_failures.items()},
            "new_entries": new_entries,
        }, indent=2))
    else:
        print_summary(patterns, new_entries, trials, molecule_failures)

    # Write to improvement ledger
    if new_entries and not args.dry_run:
        with open(IMPROVEMENT_LEDGER, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")
        if not args.json:
            print(f"\nWrote {len(new_entries)} new improvement entries to {IMPROVEMENT_LEDGER}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
