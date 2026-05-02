#!/usr/bin/env python3
"""
Securatron Session State Sync Tool

This tool synchronizes the persistent state file with the current session's progress.
It should be called at the end of each session to update the state with the latest progress.

Usage:
  python3 sync_session_state.py --project <project_id> --session <session_id> --status <status> [--findings <n>] [--notes <notes>]

Examples:
  python3 sync_session_state.py --project lab-internal --session 01KQGKSK03QY35VDPJWDVX7K30 --status success --findings 1 --notes "Template resolution issue"
  python3 sync_session_state.py --project lab-internal --session 01KQGKSK03QY35VDPJWDVX7K30 --status failed --findings 0 --notes "Empty plan"
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone


def get_state_path(project_id: str) -> Path:
    """Get the path to the state file for a project."""
    return Path.home() / ".securatron" / "projects" / project_id / "state.json"


def sync_session(project_id: str, session_id: str, status: str, findings: int = 0, notes: str = "") -> dict:
    """Sync the current session's state with the persistent state file."""
    state_path = get_state_path(project_id)
    
    # Read the current state
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
    else:
        state = {
            "project_id": project_id,
            "version": "1.0.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "current_session": None,
            "progress": {
                "total_sessions": 0,
                "sessions_with_findings": 0,
                "sessions_failed": 0,
                "atoms_built": 0,
                "atoms_promoted": 0,
                "improvements_closed": 0,
                "improvements_open": 0
            },
            "active_targets": [],
            "atoms_status": {},
            "known_issues": [],
            "priorities": [],
            "recent_sessions": []
        }
    
    # Update the current session
    state["current_session"] = session_id
    
    # Update progress counters
    state["progress"]["total_sessions"] = state["progress"].get("total_sessions", 0) + 1
    if status == "success":
        state["progress"]["sessions_with_findings"] = state["progress"].get("sessions_with_findings", 0) + 1
        if findings > 0:
            state["progress"]["sessions_with_findings"] += findings
    else:
        state["progress"]["sessions_failed"] = state["progress"].get("sessions_failed", 0) + 1
    
    # Add to recent sessions
    session_entry = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "findings": findings,
        "notes": notes
    }
    
    if "recent_sessions" not in state:
        state["recent_sessions"] = []
    state["recent_sessions"].insert(0, session_entry)
    
    # Keep only the last 20 sessions
    if len(state["recent_sessions"]) > 20:
        state["recent_sessions"] = state["recent_sessions"][:20]
    
    # Write the updated state
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    
    return state


def main():
    parser = argparse.ArgumentParser(description="Securatron Session State Sync Tool")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--session", required=True, help="Session ID")
    parser.add_argument("--status", required=True, choices=["success", "failed", "partial"],
                       help="Session status")
    parser.add_argument("--findings", type=int, default=0, help="Number of findings")
    parser.add_argument("--notes", default="", help="Notes about the session")
    
    args = parser.parse_args()
    
    try:
        state = sync_session(args.project, args.session, args.status, args.findings, args.notes)
        print(json.dumps(state, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
