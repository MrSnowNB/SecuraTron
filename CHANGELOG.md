# Changelog: SecuraTron Engine & Skill Expansion

All notable changes to the SecuraTron harness and the COBOL-to-AI pipeline are documented here.

## [v2.1.0] - 2026-05-13

### SecuraTron Engine
- **Added:** Advanced Conditional Execution for Molecules. Steps now support `condition` gates with Python expression evaluation and nested key access (e.g., `{{steps.X.result.key}}`).
- **Added:** `base_dir` injection into all tool execution contexts.
- **Improved:** `parsers.py` now includes structured output handlers for:
    - Browser Automation (`web.browser.inspect`, `interact`, `drill`).
    - Exploit Discovery (`exploit.search` via Searchsploit).
    - Post-Exploitation Reconnaissance (`post.exploit.recon`).
    - Port-specific boolean flags (e.g., `port_22_open`) in `kali.nmap` for easy molecule gating.

### New Skills & Tools
- **Added:** `ctf.full.pwn` Molecule — A complete autonomous attack chain from recon to persistence.
- **Added:** `auth.network.spray` Molecule — Multi-protocol credential auditing with conditional gating.
- **Added:** `auth.hydra` Tool — Structured atom for high-speed network authentication brute-forcing.
- **Added:** Browser Automation Suite — Playwright-backed atoms for deep DOM interaction and visual context analysis.

### COBOL-to-AI Pipeline
- **Fixed:** Port shadowing issues by ensuring single-instance `lemond` execution.
- **Optimized:** Inference configuration tuned for UMA hardware (max 3 loaded models, Vulkan contention resolved).
- **Refactored:** Harness logic migrated to atomic workers (`cobol_pipeline_worker.py`, `cobol_llm_evaluate.py`).
- **Infrastructure:** Added `FastFlowLM` to `.gitignore` to preserve repository hygiene.

---
*Built for the Strix Halo AI Homelab.*
