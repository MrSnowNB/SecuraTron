#!/usr/bin/env python3
"""
Securatron State Management Tool

Manages the persistent state file that survives context compaction.
This file is the source of truth for project state between sessions.

Usage:
  python3 manage_state.py --project <project_id> --action <action> [--key <key>] [--value <value>]

Actions:
  read      - Read the entire state file
  update    - Update a specific key-value pair
  append    - Append to a list field
  delete    - Delete a key
  validate  - Validate the state file structure

Examples:
  python3 manage_state.py --project lab-internal --action read
  python3 manage_state.py --project lab-internal --action update --key progress.total_sessions --value 88
  python3 manage_state.py --project lab-internal --action append --key recent_sessions --value '{"session_id": "abc123"}'
  python3 manage_state.py --project lab-internal --action validate
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone


def get_state_path(project_id: str) -> Path:
    """Get the path to the state file for a project."""
    return Path.home() / ".securatron" / "projects" / project_id / "state.json"


def read_state(project_id: str) -> dict:
    """Read the state file for a project."""
    state_path = get_state_path(project_id)
    if not state_path.exists():
        return {}
    with open(state_path) as f:
        return json.load(f)


def write_state(project_id: str, state: dict) -> None:
    """Write the state file for a project."""
    state_path = get_state_path(project_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def update_key(state: dict, key: str, value: any) -> dict:
    """Update a specific key in the state."""
    keys = key.split(".")
    current = state
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    return state


def append_to_list(state: dict, key: str, value: any) -> dict:
    """Append a value to a list field in the state."""
    keys = key.split(".")
    current = state
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]
    if keys[-1] not in current:
        current[keys[-1]] = []
    if not isinstance(current[keys[-1]], list):
        raise ValueError(f"Field {key} is not a list")
    current[keys[-1]].append(value)
    return state


def delete_key(state: dict, key: str) -> dict:
    """Delete a key from the state."""
    keys = key.split(".")
    current = state
    for k in keys[:-1]:
        if k not in current:
            return state
        current = current[k]
    if keys[-1] in current:
        del current[keys[-1]]
    return state


def validate_state(state: dict) -> tuple[bool, list[str]]:
    """Validate the state file structure."""
    errors = []
    
    # Check required fields
    required_fields = ["project_id", "version", "last_updated"]
    for field in required_fields:
        if field not in state:
            errors.append(f"Missing required field: {field}")
    
    # Check progress fields
    if "progress" in state:
        progress_fields = ["total_sessions", "sessions_with_findings", "sessions_failed",
                          "atoms_built", "atoms_promoted", "improvements_closed", "improvements_open"]
        for field in progress_fields:
            if field not in state["progress"]:
                errors.append(f"Missing progress field: {field}")
    
    # Check atoms_status
    if "atoms_status" in state:
        for atom_id, atom_data in state["atoms_status"].items():
            if "status" not in atom_data:
                errors.append(f"Missing status for atom: {atom_id}")
            if "trials" not in atom_data:
                errors.append(f"Missing trials for atom: {atom_id}")
    
    # Check priorities
    if "priorities" in state:
        for priority in state["priorities"]:
            if "id" not in priority:
                errors.append("Priority missing 'id' field")
            if "title" not in priority:
                errors.append("Priority missing 'title' field")
            if "status" not in priority:
                errors.append("Priority missing 'status' field")
    
    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="Securatron State Management Tool")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--action", required=True, choices=["read", "update", "append", "delete", "validate"],
                       help="Action to perform")
    parser.add_argument("--key", help="Key to update/delete/append")
    parser.add_argument("--value", help="Value to update/append")
    
    args = parser.parse_args()
    
    try:
        state = read_state(args.project)
        
        if args.action == "read":
            print(json.dumps(state, indent=2))
        
        elif args.action == "update":
            if not args.key or not args.value:
                print("Error: --key and --value are required for update action", file=sys.stderr)
                sys.exit(1)
            try:
                value = json.loads(args.value)
            except json.JSONDecodeError:
                value = args.value
            state = update_key(state, args.key, value)
            write_state(args.project, state)
            print(f"Updated {args.key} to {args.value}")
        
        elif args.action == "append":
            if not args.key or not args.value:
                print("Error: --key and --value are required for append action", file=sys.stderr)
                sys.exit(1)
            try:
                value = json.loads(args.value)
            except json.JSONDecodeError:
                value = args.value
            state = append_to_list(state, args.key, value)
            write_state(args.project, state)
            print(f"Appended to {args.key}")
        
        elif args.action == "delete":
            if not args.key:
                print("Error: --key is required for delete action", file=sys.stderr)
                sys.exit(1)
            state = delete_key(state, args.key)
            write_state(args.project, state)
            print(f"Deleted {args.key}")
        
        elif args.action == "validate":
            valid, errors = validate_state(state)
            if valid:
                print("State file is valid")
            else:
                print("State file has errors:")
                for error in errors:
                    print(f"  - {error}")
                sys.exit(1)
        
    except FileNotFoundError:
        print(f"Error: State file not found for project {args.project}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in state file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
