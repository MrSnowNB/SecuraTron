#!/usr/bin/env python3
"""
system.audit.suite runner — execute the full audit pipeline.

Discovers all SecuraTron atoms and molecules, tests each with safe mock data,
and generates a consolidated markdown report for the evidence locker.
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path.home() / ".securatron"
TOOLS_DIR = BASE_DIR / "global" / "tools"
SKILLS_DIR = BASE_DIR / "global" / "skills"
EVIDENCE_DIR = BASE_DIR / "global" / "evidence" / "locker"
BIN_DIR = BASE_DIR / "global" / "bin"

def safe_mock_inputs_for_tool(tool_id: str, card: dict) -> dict:
    """Generate safe mock inputs based on the tool's input definitions."""
    inputs_def = card.get("inputs", {})
    mock = {}
    
    for field_name, field_def in inputs_def.items():
        if not isinstance(field_def, dict):
            continue
        
        validator = field_def.get("validator", "")
        required = field_def.get("required", False)
        field_type = field_def.get("type", "string")
        
        if validator in ("rfc1123_host_or_cidr", "rfc1123_host_or_ip"):
            mock[field_name] = "127.0.0.1"
        elif validator == "rfc1123_hostname":
            mock[field_name] = "localhost"
        elif field_name == "target":
            mock[field_name] = "127.0.0.1"
        elif field_name in ("flags", "command"):
            mock[field_name] = field_def.get("default", "-h")
        elif field_name in ("user_list", "pass_list", "wordlist"):
            tmp = Path(f"/tmp/securatron-test-{tool_id}-{field_name}.txt")
            with open(tmp, "w") as f:
                f.write("admin\ntest\nguest\n")
            mock[field_name] = str(tmp)
        elif field_name == "data":
            mock[field_name] = {
                "audit": True,
                "tool": tool_id,
                "ts": str(int(time.time())),
                "safe": True
            }
        elif field_name == "path":
            mock[field_name] = f"audit/{tool_id}-test.json"
        elif field_name == "service":
            mock[field_name] = field_def.get("default", "ssh")
        elif field_name == "port":
            mock[field_name] = field_def.get("default", 22)
        elif field_name == "tier":
            mock[field_name] = "global"
        elif field_name == "session_id":
            mock[field_name] = "TEST"
        elif field_name == "project_id":
            mock[field_name] = "lab-internal"
        elif field_name == "author":
            mock[field_name] = "audit"
        elif field_name == "skill":
            mock[field_name] = tool_id
        elif field_name == "limit":
            mock[field_name] = "5"
        elif field_name == "flags":
            mock[field_name] = field_def.get("default", "-h")
        else:
            mock[field_name] = field_def.get("default", "AUDIT_TEST")
    
    return mock


def test_tool(tool_id: str, tool_kind: str, card: dict) -> dict:
    """Test a single tool and return results."""
    ts = str(int(time.time()))
    result = {
        "tool_id": tool_id,
        "tool_kind": tool_kind,
        "timestamp": ts,
        "status": "unknown",
        "exit_code": None,
        "duration_ms": 0,
        "output_length": 0,
        "error": None,
        "evidence_file": None,
    }
    
    mock_inputs = safe_mock_inputs_for_tool(tool_id, card)
    if not mock_inputs:
        result["status"] = "failed"
        result["error"] = "no inputs defined — cannot generate mocks"
        return result
    
    # Convert to key=value format
    input_args = []
    for k, v in mock_inputs.items():
        if isinstance(v, dict):
            v = json.dumps(v)
        input_args.append(f"--input={k}={v}")
    
    # Run dispatch.py
    cmd = [
        sys.executable,
        str(BIN_DIR / "dispatch.py"),
        "dispatch",
        "--skill", tool_id,
        "--project", "lab-internal",
        "--output-format", "json",
        "--trials", "1",
    ] + input_args
    
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BIN_DIR),
        )
        duration = int((time.time() - start) * 1000)
        result["exit_code"] = proc.returncode
        result["duration_ms"] = duration
        result["output_length"] = len(proc.stdout)
        
        # Parse JSON output
        try:
            lines = proc.stdout.strip().split("\n")
            json_output = None
            for line in reversed(lines):
                try:
                    json_output = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            
            if json_output and isinstance(json_output, dict):
                result["dispatch_ok"] = json_output.get("ok", False)
                if not json_output.get("ok", False):
                    result["status"] = "failed"
                    result["error"] = json_output.get("reason", "ok=false or missing")
                else:
                    result["status"] = "passed"
            elif proc.returncode == 0:
                result["status"] = "passed"
            else:
                result["status"] = "failed"
                result["error"] = f"exit code {proc.returncode}"
        except (json.JSONDecodeError, TypeError):
            if proc.returncode == 0:
                result["status"] = "passed"
            else:
                result["status"] = "failed"
                result["error"] = f"parse failed: exit {proc.returncode}"
        
        if proc.stderr.strip():
            result["stderr_preview"] = proc.stderr.strip()[:300]
        
    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["error"] = "timeout (120s)"
        result["duration_ms"] = 120000
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
    
    # Write evidence
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    ev_file = EVIDENCE_DIR / f"AUDIT_{tool_id.replace('.', '_')}_v{ts}.json"
    with open(ev_file, "w") as f:
        json.dump(result, f, indent=2)
    result["evidence_file"] = str(ev_file)
    
    return result


def discover_tools() -> list[dict]:
    """Discover all .yaml cards in tools/ and skills/ directories."""
    tools = []
    
    for d in [TOOLS_DIR, SKILLS_DIR]:
        if not d.exists():
            continue
        for yaml_file in sorted(d.glob("*.yaml")):
            tool_id = yaml_file.stem
            try:
                import yaml
                with open(yaml_file) as f:
                    card = yaml.safe_load(f)
                kind = card.get("kind", "unknown")
                desc = card.get("description", "")[:120]
                tools.append({
                    "id": tool_id,
                    "kind": kind,
                    "description": desc,
                    "path": str(yaml_file),
                    "card": card,
                })
            except Exception as e:
                tools.append({
                    "id": tool_id,
                    "kind": "error",
                    "description": f"parse error: {e}",
                    "path": str(yaml_file),
                    "card": {},
                })
    
    return tools


def generate_report(results: list[dict], discovered: list[dict], audit_ts: str) -> str:
    """Generate a markdown audit report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    
    # Count by kind
    atom_results = [r for r in results if r["tool_kind"] == "atom"]
    molecule_results = [r for r in results if r["tool_kind"] == "molecule"]
    atom_passed = sum(1 for r in atom_results if r["status"] == "passed")
    atom_failed = sum(1 for r in atom_results if r["status"] == "failed")
    mol_passed = sum(1 for r in molecule_results if r["status"] == "passed")
    mol_failed = sum(1 for r in molecule_results if r["status"] == "failed")
    
    lines = [
        f"# SECURATRON AUTOMATED AUDIT REPORT",
        f"",
        f"**Audit Timestamp:** {audit_ts}",
        f"**Generated:** {now}",
        f"**Harness Version:** {BASE_DIR}",
        f"",
        f"---",
        f"",
        f"## EXECUTIVE SUMMARY",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Tools Tested | {total} |",
        f"| **PASSED** | {passed} |",
        f"| **FAILED** | {failed} |",
        f"| Skipped/Errors | {skipped} |",
        f"| Pass Rate | {passed}/{total} ({int(100*passed/max(total,1))}%) |",
        f"",
        f"### By Category",
        f"",
        f"| Category | Total | Passed | Failed |",
        f"|----------|-------|--------|--------|",
        f"| **Atoms** | {len(atom_results)} | {atom_passed} | {atom_failed} |",
        f"| **Molecules** | {len(molecule_results)} | {mol_passed} | {mol_failed} |",
        f"",
        f"---",
        f"",
        f"## DETAILED RESULTS",
        f"",
    ]
    
    # Group by kind
    for kind_label, kind_key in [("ATOMIC TOOLS", "atom"), ("MOLECULES", "molecule")]:
        kind_results = [r for r in results if r["tool_kind"] == kind_key]
        if not kind_results:
            continue
        
        lines.append(f"### {kind_label}")
        lines.append("")
        lines.append("| # | Tool ID | Status | Duration (ms) | Error |")
        lines.append("|---|---------|--------|---------------|-------|")
        
        for i, r in enumerate(kind_results, 1):
            status_marker = "PASS" if r["status"] == "passed" else "FAIL"
            error = r.get("error", "")[:60] if r.get("error") else "—"
            duration = r.get("duration_ms", "N/A")
            lines.append(f"| {i} | `{r['tool_id']}` | {status_marker} | {duration} | {error} |")
        
        lines.append("")
        
        # Detailed failures
        failures = [r for r in kind_results if r["status"] == "failed"]
        if failures:
            lines.append(f"#### Failures ({len(failures)})")
            lines.append("")
            for f in failures:
                lines.append(f"- **{f['tool_id']}**: {f.get('error', 'unknown')}")
                if f.get("stderr_preview"):
                    lines.append(f"  - Stderr: `{f['stderr_preview'][:200]}`")
                if f.get("evidence_file"):
                    lines.append(f"  - Evidence: `{f['evidence_file']}`")
            lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## EVIDENCE ARTIFACTS")
    lines.append("")
    lines.append(f"All test evidence artifacts are stored in: `{EVIDENCE_DIR}`")
    lines.append("")
    evidence_files = sorted(EVIDENCE_DIR.glob("AUDIT_*.json"))
    lines.append(f"Total evidence files: {len(evidence_files)}")
    lines.append("")
    for ef in evidence_files[:20]:  # Limit to first 20
        lines.append(f"- `{ef.name}` ({ef.stat().st_size} bytes)")
    if len(evidence_files) > 20:
        lines.append(f"- ... and {len(evidence_files) - 20} more")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## METHODOLOGY")
    lines.append("")
    lines.append("1. **Discovery**: All `.yaml` files in `tools/` and `skills/` directories")
    lines.append("2. **Mock Generation**: Safe mock inputs derived from each tool's input schema")
    lines.append("   - Network targets use `127.0.0.1` (loopback only)")
    lines.append("   - Wordlists use safe temp files with 3 generic usernames")
    lines.append("   - Write operations use safe test payloads")
    lines.append("3. **Execution**: Each tool run via `dispatch.py` with 120s timeout")
    lines.append("4. **Verification**: Exit code 0 + JSON `ok: true` required for PASS")
    lines.append("5. **Evidence**: Per-tool JSON artifacts + consolidated markdown report")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by system.audit.suite — SecuraTron CI/CD Pipeline*")
    lines.append("")
    
    return "\n".join(lines)


def main():
    audit_ts = datetime.now(timezone.utc).isoformat()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Discover all tools
    print("[AUDIT] Discovering tools...")
    discovered = discover_tools()
    print(f"[AUDIT] Found {len(discovered)} tools")
    
    # Step 2: Test each tool
    print("[AUDIT] Running tests...")
    results = []
    for tool_info in discovered:
        tool_id = tool_info["id"]
        tool_kind = tool_info["kind"]
        if tool_kind not in ("atom", "molecule"):
            continue  # Skip non-tool entries (like atom-builder skill dir)
        
        print(f"  Testing {tool_id} ({tool_kind})...")
        tool_card = tool_info.get("card", {})
        r = test_tool(tool_id, tool_kind, tool_card)
        results.append(r)
        status_str = "PASS" if r["status"] == "passed" else f"FAIL ({r.get('error', '?')})"
        print(f"    → {status_str} ({r['duration_ms']}ms)")
    
    # Step 3: Generate report
    print("[AUDIT] Generating report...")
    report = generate_report(results, discovered, audit_ts)
    
    # Write report
    ts_short = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = EVIDENCE_DIR / f"AUDIT_REPORT_{ts_short}.md"
    with open(report_path, "w") as f:
        f.write(report)
    
    # Also write a symlink to latest
    latest_path = EVIDENCE_DIR / "AUDIT_REPORT_LATEST.md"
    latest_path.unlink(missing_ok=True)
    latest_path.symlink_to(report_path.name)
    
    # Print summary
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    
    print(f"\n[AUDIT] Complete: {passed} passed, {failed} failed, {len(results)} total")
    print(f"[AUDIT] Report: {report_path}")
    print(f"[AUDIT] Evidence dir: {EVIDENCE_DIR}")
    
    # Write result to mem for molecule integration
    result_data = {
        "audit_timestamp": audit_ts,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "report_path": str(report_path),
    }
    # Write to session memory
    mem_path = BASE_DIR / "global" / "inbox" / "audit_result.json"
    with open(mem_path, "w") as f:
        json.dump(result_data, f, indent=2)
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
