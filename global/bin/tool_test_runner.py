#!/usr/bin/env python3
"""
system.tool.test runner — execute a SecuraTron atom or molecule with safe mock data
and verify its output. Called by the auth.network.test atom.

Arguments (positional):
  tool_id          — Atom or molecule ID to test (e.g. "kali.nmap")
  tool_kind        — "atom" or "molecule"
  evidence_dir     — Absolute path to evidence/locker directory
  project_id       — Project ID for dispatch

Output: JSON object with test results written to evidence locker.
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path

BASE_DIR = Path.home() / ".securatron"
TOOLS_DIR = BASE_DIR / "global" / "tools"
SKILLS_DIR = BASE_DIR / "global" / "skills"
EVIDENCE_DIR = BASE_DIR / "global" / "evidence" / "locker"

def safe_mock_inputs(tool_id: str, tool_kind: str) -> dict:
    """Return safe mock inputs based on the tool's expected inputs."""
    # Load the card to inspect its inputs
    if tool_kind == "atom":
        card_path = TOOLS_DIR / f"{tool_id}.yaml"
    else:
        card_path = SKILLS_DIR / f"{tool_id}.yaml"
    
    if not card_path.exists():
        return {"_error": f"Card not found: {card_path}"}
    
    import yaml
    with open(card_path) as f:
        card = yaml.safe_load(f)
    
    inputs_def = card.get("inputs", {})
    mock = {}
    
    for field_name, field_def in inputs_def.items():
        if not isinstance(field_def, dict):
            continue
        field_type = field_def.get("type", "string")
        required = field_def.get("required", False)
        
        # Skip required validator-based fields for safety
        validator = field_def.get("validator", "")
        
        if validator in ("rfc1123_host_or_cidr", "rfc1123_host_or_ip"):
            mock[field_name] = "127.0.0.1"
        elif validator == "rfc1123_hostname":
            mock[field_name] = "localhost"
        elif field_name == "target":
            mock[field_name] = "127.0.0.1"
        elif field_name in ("flags", "command"):
            mock[field_name] = field_def.get("default", "-h")
        elif field_name in ("user_list", "pass_list", "wordlist"):
            # Create a safe temporary wordlist
            tmp = Path(f"/tmp/securatron-test-{tool_id}-{field_name}.txt")
            with open(tmp, "w") as wf:
                wf.write("admin\ntest\nguest\n")
            mock[field_name] = str(tmp)
        elif field_name == "data":
            # For write operations, use a safe test payload
            mock[field_name] = {"test": "audit_data", "tool": tool_id, "ts": str(int(time.time()))}
        elif field_name == "path":
            mock[field_name] = f"evidence/{tool_id}-test.json"
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
        elif field_name == "target_ip" or field_name == "hostname":
            mock[field_name] = "127.0.0.1"
        else:
            # Generic string fallback: use short safe value
            mock[field_name] = field_def.get("default", "TEST")
    
    return mock


def run_test(tool_id: str, tool_kind: str, evidence_dir: str, project_id: str) -> dict:
    """Execute a single tool test and return results."""
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
    
    # Get safe mock inputs
    mock_inputs = safe_mock_inputs(tool_id, tool_kind)
    if "_error" in mock_inputs:
        result["status"] = "failed"
        result["error"] = mock_inputs["_error"]
        return result
    
    # Convert inputs to dispatch.py key=value format
    input_args = []
    for k, v in mock_inputs.items():
        if isinstance(v, dict):
            v = json.dumps(v)
        input_args.append(f"--input={k}={v}")
    
    # Call dispatch.py
    dispatch_cmd = [
        sys.executable,
        str(BASE_DIR / "global" / "bin" / "dispatch.py"),
        "dispatch",
        "--skill", tool_id,
        "--project", project_id,
        "--output-format", "json",
        "--trials", "1",
    ] + input_args
    
    start = time.time()
    try:
        proc = subprocess.run(
            dispatch_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR / "global" / "bin"),
        )
        duration = int((time.time() - start) * 1000)
        
        result["exit_code"] = proc.returncode
        result["duration_ms"] = duration
        result["output_length"] = len(proc.stdout)
        
        # Parse dispatch output for ok status
        try:
            output_lines = proc.stdout.strip().split("\n")
            # Find the JSON output (last valid JSON block)
            json_output = None
            for line in reversed(output_lines):
                try:
                    json_output = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            
            if json_output and isinstance(json_output, dict):
                result["dispatch_ok"] = json_output.get("ok", False)
                if not json_output.get("ok", True):
                    result["status"] = "failed"
                    result["error"] = json_output.get("reason", "dispatch returned ok=false")
                else:
                    result["status"] = "passed"
            elif proc.returncode != 0:
                result["status"] = "failed"
                result["error"] = f"dispatch exit code {proc.returncode}"
            else:
                result["status"] = "passed"
        except (json.JSONDecodeError, TypeError):
            if proc.returncode == 0:
                result["status"] = "passed"
            else:
                result["status"] = "failed"
                result["error"] = f"parse error: exit {proc.returncode}"
        
        # Capture stderr for debugging
        if proc.stderr.strip():
            result["stderr_preview"] = proc.stderr.strip()[:500]
        
    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["error"] = "timeout (120s exceeded)"
        result["duration_ms"] = 120000
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
    
    # Write evidence
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_file = EVIDENCE_DIR / f"AUDIT_{tool_id.replace('.', '_')}_v{ts}.json"
    with open(evidence_file, "w") as f:
        json.dump(result, f, indent=2)
    result["evidence_file"] = str(evidence_file)
    
    return result


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: tool_test_runner.py <tool_id> <tool_kind> <evidence_dir> [project_id]"}))
        sys.exit(1)
    
    tool_id = sys.argv[1]
    tool_kind = sys.argv[2]
    evidence_dir = sys.argv[3]
    project_id = sys.argv[4] if len(sys.argv) > 4 else "lab-internal"
    
    # Override evidence dir
    global EVIDENCE_DIR
    EVIDENCE_DIR = Path(evidence_dir)
    
    result = run_test(tool_id, tool_kind, evidence_dir, project_id)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
