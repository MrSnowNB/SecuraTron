# SecuraTron: Autonomous Security Orchestration Harness

SecuraTron is a first-principles-based security harness designed for autonomous agent operations on AMD Strix Halo hardware. It implements a strictly gated tool-chaining engine, a multi-tier persistent memory organ, and a recursive self-improvement loop.

## Core Architecture

SecuraTron is built on three foundational pillars:

### 1. The Multi-Tier Memory Organ
- **Tier 0 (Hot):** Volatile session context and scratchpad.
- **Tier 1 (Warm):** Rebuildable SQLite + FTS5 index (`index.db`) for rapid discovery.
- **Tier 2 (Cold):** Immutable, append-only JSONL ledgers and Markdown post-mortems (Source of Truth).

### 2. The Gated Dispatch Engine
- **Atoms:** Atomic tool wrappers (e.g., `kali.nmap`, `web.nikto`).
- **Molecules:** Composed DAG workflows (e.g., `recon.host.full`) with topological sorting and recursive template resolution.
- **The Gate:** Strict enforcement of project scope, input validation, and execution preconditions.

### 3. The Self-Improvement Loop (SIL)
- **Observe:** Automatic failure classification into a canonical taxonomy (FM-1 to FM-11).
- **Extract:** Pattern detection across trial ledgers to identify recurring bottlenecks.
- **Act:** Formal Improvement Tickets (IT-NNN) track fixes to cards, parsers, or engine logic.
- **Verify:** Mandatory evidence-based closing of tickets via trial re-runs.

### 4. Persistent State Management
- **Context Persistence:** Maintains project-level state (`state.json`) to survive context compaction and session restarts.
- **State Tools:** Standardized CLI utilities (`manage_state.py`, `sync_session_state.py`) for atomic state updates.
- **Continuity:** Ensures autonomous loops pick up exactly where they left off by reading persistent priorities and known issues.

## Directory Structure

```text
~/.securatron/
├── global/
│   ├── bin/           # Harness binaries (dispatch, reindex, analyze)
│   ├── charters/      # Governance (Memory Charter, Inbox Charter)
│   ├── doctrine/      # Operational rules (SIL, fp-loop, memory-rules)
│   ├── ledger/        # Cold canonical trial and improvement logs
│   ├── post-mortems/  # Knowledge compounding for every skill
│   ├── skills/        # Hardened Molecules (v1+)
│   └── tools/         # Draft Atoms and Molecules
├── projects/          # Engagement-specific scope and findings
├── sessions/          # Active execution traces and artifacts
└── terminal/          # Multi-modal SOC interface (v2.0)
```

## Quick Start

### 1. Start the Brain
```bash
sudo systemctl start lemond
```

### 2. Start the Tools (MCP)
```bash
python3 ~/.securatron/global/bin/mcp_server.py
```

### 3. Run a Recon Molecule
```bash
python3 ~/.securatron/global/bin/dispatch.py --skill recon.host.full --input target=127.0.0.1 --project lab-internal
```

## Operational Doctrine

SecuraTron adheres to the **Hermes Soul** protocol:
- **Verify Before Success:** Never claim completion without artifact proof.
- **Canonical Schema Always:** Data integrity is non-negotiable.
- **Surfaced Failure Over Silent Pass:** Failures are the primary source of improvement.

---
*Built for the Strix Halo AI Homelab. Engineered from first principles.*
