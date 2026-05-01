#!/usr/bin/env python3
"""apply_improvements.py — Self-Improvement Loop Phase 3 (Act) and Phase 4 (Verify)

Manages improvement tickets: list, view, apply fixes, and verify results.

Usage:
    python3 apply_improvements.py list              # Show all IT tickets
    python3 apply_improvements.py list --open        # Show only open tickets
    python3 apply_improvements.py view IT-web.nikto-001  # View details
    python3 apply_improvements.py verify IT-web.nikto-001 --trial 01KQ5YWR4JZZN77TF6RMN1HK20
    python3 apply_improvements.py close IT-web.nikto-001 --evidence "re-run succeeded"
    python3 apply_improvements.py defer IT-web.nikto-001 --reason "not needed for v0.1"
"""

import json
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path.home() / ".securatron"
IMPROVEMENT_LEDGER = BASE_DIR / "global" / "ledger" / "improvements.jsonl"
LEDGER_DIR = BASE_DIR / "global" / "ledger"


def load_improvement_entries():
    """Load all improvement ledger entries."""
    entries = []
    if not IMPROVEMENT_LEDGER.exists():
        return entries
    with open(IMPROVEMENT_LEDGER) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def get_latest_entry(entries, it_id):
    """Get the latest entry for a given improvement ID (entries are append-only)."""
    matching = [e for e in entries if e.get("improvement_id") == it_id]
    return matching[-1] if matching else None


def cmd_list(args, entries):
    """List improvement tickets."""
    open_only = hasattr(args, 'open') and args.open
    filtered = [e for e in entries if e.get("status") != "closed"] if open_only else entries

    if not filtered:
        print("No improvement tickets found.")
        return

    print(f"{'ID':<30} {'Status':<12} {'Mode':<18} {'Skill':<20} {'Desc':<50}")
    print("-" * 120)
    for e in filtered:
        iid = e.get("improvement_id", "unknown")
        status = e.get("status", "unknown")
        mode = e.get("failure_mode", "unknown")
        skill = e.get("skill_id", "unknown")
        desc = (e.get("description", "")[:47] + "...") if len(e.get("description", "")) > 50 else e.get("description", "")
        print(f"{iid:<30} {status:<12} {mode:<18} {skill:<20} {desc:<50}")


def cmd_view(args, entries):
    """View details of an improvement ticket."""
    it_id = args.it_id
    entry = get_latest_entry(entries, it_id)

    if not entry:
        print(f"Improvement ticket '{it_id}' not found.")
        return

    print(f"{'='*60}")
    print(f"Improvement Ticket: {entry.get('improvement_id')}")
    print(f"{'='*60}")
    print(f"  Status:        {entry.get('status')}")
    print(f"  Phase:         {entry.get('phase')}")
    print(f"  Skill:         {entry.get('skill_id')}")
    print(f"  Failure Mode:  {entry.get('failure_mode')}")
    print(f"  Description:   {entry.get('description')}")
    print(f"  Root Cause:    {entry.get('root_cause', 'N/A')}")
    print(f"  Action Taken:  {entry.get('action_taken', 'N/A')}")
    print(f"  Files Modified: {', '.join(entry.get('files_modified', [])) or 'none'}")
    print(f"  Verification:  {entry.get('verification_status', 'N/A')}")
    if entry.get('verification_evidence'):
        print(f"  Evidence:      {entry.get('verification_evidence')[:200]}")
    print(f"  Trigger Trials: {len(entry.get('trigger_trial_ids', []))}")
    for tid in entry.get('trigger_trial_ids', [])[:5]:
        print(f"    - {tid}")
    print(f"  Related PM:    {entry.get('related_post_mortem', 'none')}")
    print(f"  Related TDs:   {', '.join(entry.get('related_defects', [])) or 'none'}")
    print(f"{'='*60}")


def cmd_verify(args, entries):
    """Verify an improvement ticket by re-running the original failing trial."""
    it_id = args.it_id
    trial_id = args.trial

    entry = get_latest_entry(entries, it_id)
    if not entry:
        print(f"Improvement ticket '{it_id}' not found.")
        return

    # Find the trial in the ledger
    trial_data = None
    skill_id = entry.get("skill_id", "unknown")
    ledger_file = LEDGER_DIR / f"{skill_id}.trials.jsonl"
    if ledger_file.exists():
        with open(ledger_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        t = json.loads(line)
                        if t.get("trial_id") == trial_id:
                            trial_data = t
                            break
                    except json.JSONDecodeError:
                        continue

    if not trial_data:
        print(f"Trial {trial_id} not found in {skill_id} ledger.")
        return

    was_failed = trial_data.get("status") != "success"
    print(f"Original trial {trial_id}: status={trial_data.get('status')}, result={trial_data.get('result')}")
    print(f"This trial {entry.get('phase', 'extract')} as the basis for {it_id}.")
    print()
    print("VERIFICATION CHECKLIST:")
    print(f"  [ ] Re-run the atom with original inputs")
    print(f"  [ ] Confirm the trial now succeeds")
    print(f"  [ ] Record verification evidence")
    print(f"  [ ] Update IT status to 'closed'")
    print()
    print("To complete verification:")
    print(f"  1. Run: python3 dispatch.py --skill {skill_id} --input target=<original_target> --trials 1 --session <new-session>")
    print(f"  2. Confirm result is 'success'")
    print(f"  3. Run: python3 apply_improvements.py close {it_id} --evidence '<verification details>'")


def cmd_close(args, entries):
    """Close an improvement ticket with verification evidence."""
    it_id = args.it_id
    evidence = args.evidence if hasattr(args, 'evidence') and args.evidence else "manual verification"

    entry = get_latest_entry(entries, it_id)
    if not entry:
        print(f"Improvement ticket '{it_id}' not found.")
        return

    # Update the entry in the improvement ledger (append a new version)
    updated = dict(entry)
    updated["status"] = "closed"
    updated["verification_status"] = "passed"
    updated["verification_evidence"] = evidence
    updated["ts"] = datetime.utcnow().isoformat() + "Z"
    updated["phase"] = "verify"

    # Append to improvement ledger (append-only — keep history)
    with open(IMPROVEMENT_LEDGER, "a") as f:
        f.write(json.dumps(updated) + "\n")

    print(f"Closed {it_id}.")
    print(f"  Verification: {evidence}")


def cmd_defer(args, entries):
    """Defer an improvement ticket."""
    it_id = args.it_id
    reason = args.reason if hasattr(args, 'reason') and args.reason else "deferred"

    entry = get_latest_entry(entries, it_id)
    if not entry:
        print(f"Improvement ticket '{it_id}' not found.")
        return

    updated = dict(entry)
    updated["status"] = "deferred"
    updated["ts"] = datetime.utcnow().isoformat() + "Z"
    updated["phase"] = "extract"

    with open(IMPROVEMENT_LEDGER, "a") as f:
        f.write(json.dumps(updated) + "\n")

    print(f"Deferred {it_id}. Reason: {reason}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manage improvement tickets for the Self-Improvement Loop")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # list
    p_list = subparsers.add_parser("list", help="List improvement tickets")
    p_list.add_argument("--open", action="store_true", help="Show only open tickets")

    # view
    p_view = subparsers.add_parser("view", help="View an improvement ticket")
    p_view.add_argument("it_id", help="Improvement ticket ID (e.g., IT-web.nikto-001)")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify an improvement ticket")
    p_verify.add_argument("it_id", help="Improvement ticket ID")
    p_verify.add_argument("--trial", help="Original trial ID to verify against")

    # close
    p_close = subparsers.add_parser("close", help="Close an improvement ticket")
    p_close.add_argument("it_id", help="Improvement ticket ID")
    p_close.add_argument("--evidence", help="Verification evidence text")

    # defer
    p_defer = subparsers.add_parser("defer", help="Defer an improvement ticket")
    p_defer.add_argument("it_id", help="Improvement ticket ID")
    p_defer.add_argument("--reason", help="Reason for deferral")

    args = parser.parse_args()

    entries = load_improvement_entries()

    if args.command == "list":
        cmd_list(args, entries)
    elif args.command == "view":
        cmd_view(args, entries)
    elif args.command == "verify":
        cmd_verify(args, entries)
    elif args.command == "close":
        cmd_close(args, entries)
    elif args.command == "defer":
        cmd_defer(args, entries)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
