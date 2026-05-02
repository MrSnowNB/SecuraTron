# Doctrine: State Management

## Overview

Securatron uses a persistent state file to maintain project context between sessions and during context compaction. This state file is the source of truth for:
- Current progress and priorities
- Known issues and their status
- Atom status and trial results
- Active targets and their scan history
- Recent session history

## State File Location

`~/.securatron/projects/<project_id>/state.json`

## State File Schema

```json
{
  "project_id": "lab-internal",
  "version": "1.0.0",
  "last_updated": "2026-05-02T12:00:00Z",
  "current_session": null,
  "progress": {
    "total_sessions": 87,
    "sessions_with_findings": 9,
    "sessions_failed": 78,
    "atoms_built": 3,
    "atoms_promoted": 0,
    "improvements_closed": 4,
    "improvements_open": 0
  },
  "active_targets": [...],
  "atoms_status": [...],
  "known_issues": [...],
  "priorities": [...],
  "recent_sessions": [...]
}
```

## When to Update State

The agent MUST update the state file:
1. **At the start of a session** - Read the state to understand current progress
2. **After each tool call** - Update progress if the tool call changed the state
3. **At the end of a session** - Sync the session's results to the state

## How to Update State

Use the `manage_state.py` tool:

```bash
# Read the current state
python3 ~/.securatron/global/bin/manage_state.py --project lab-internal --action read

# Update a key
python3 ~/.securatron/global/bin/manage_state.py --project lab-internal --action update --key progress.total_sessions --value 88

# Append to a list
python3 ~/.securatron/global/bin/manage_state.py --project lab-internal --action append --key recent_sessions --value '{"session_id": "abc123"}'

# Delete a key
python3 ~/.securatron/global/bin/manage_state.py --project lab-internal --action delete --key current_session

# Validate the state
python3 ~/.securatron/global/bin/manage_state.py --project lab-internal --action validate
```

Use the `sync_session_state.py` tool to sync the current session's results:

```bash
python3 ~/.securatron/global/bin/sync_session_state.py --project lab-internal --session 01KQGKSK03QY35VDPJWDVX7K30 --status success --findings 1 --notes "Template resolution issue"
```

## State Updates During Session

The agent should update the state file after:
1. **Building an atom** - Update `atoms_status` with the new atom's status
2. **Running a trial** - Update the atom's trial count and success rate
3. **Discovering an issue** - Add to `known_issues` with status "open"
4. **Fixing an issue** - Update the issue's status to "fixed"
5. **Completing a priority** - Update the priority's status to "completed"
6. **Starting a new priority** - Add a new priority to the list

## State Restoration After Compaction

When context is compacted, the agent should:
1. Read the state file to understand current progress
2. Update the `current_session` field with the new session ID
3. Continue working from where the previous session left off

## State File Maintenance

The state file should be:
- **Machine-readable** - JSON format for easy parsing
- **Incrementally updated** - Don't rewrite the entire file, just update the relevant fields
- **Validated** - Run validation after updates to ensure the structure is correct
- **Compressed** - Keep the file size under 10KB by archiving old data

## Verification (May 2, 2026)

The state management system has been verified through a 5-phase gated validation suite:
- **Phase 1 (Core):** Read/Write/Append/Delete operations confirmed.
- **Phase 2 (Sync):** Session success/fail sync with counter updates confirmed.
- **Phase 3 (Compaction):** State survival through simulated context loss confirmed.
- **Phase 4 (Automation):** Cron job integration confirmed.
- **Phase 5 (Errors):** Graceful error handling for invalid keys/actions confirmed.

**Result:** PASS (14/14 tests). See `projects/lab-internal/STATE_TEST_REPORT.md` for details.

## Future Enhancements (Post-Test)

1. **Delete by ID:** Implement specific item deletion for list fields (currently only top-level).
2. **Automatic Backups:** Create a `.state.json.bak` before every write operation.
3. **Atomic Transactions:** Implement file locking to prevent corruption during simultaneous writes.
