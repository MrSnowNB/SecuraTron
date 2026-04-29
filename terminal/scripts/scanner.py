#!/usr/bin/env python3
"""
Securatron Scanner Integration
First Principles Architecture — Scan Integration Layer

Usage:
    python3 scanner.py nmap <target> [--ports <ports>] [--save]
    python3 scanner.py nikto <target> [--save]
    python3 scanner.py full <target>  -- Full scan (nmap + nikto)
"""

import json
import subprocess
import sys
import os
import urllib.request

LLM_URL = "http://localhost:13305"
SCAN_DIR = "/tmp/securatron_scans"

def ensure_scan_dir():
    os.makedirs(SCAN_DIR, exist_ok=True)

def run_command(cmd, timeout=120):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1

def nmap_scan(target, ports="1-10000", save=False):
    """Run Nmap scan and return results."""
    print(f"[SCAN] Running Nmap on {target} (ports: {ports})...")
    
    stdout, stderr, rc = run_command(
        f"nmap -sV -sC -p {ports} -oX - {target}"
    )
    
    if rc != 0:
        print(f"[SCAN] Nmap failed: {stderr}")
        return None
    
    # Parse XML output to JSON
    scan_data = {
        "type": "nmap",
        "target": target,
        "ports": ports,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "raw_output": stdout[:2000]  # Limit raw output
    }
    
    # Extract basic info
    if "Host is up" in stdout:
        scan_data["status"] = "up"
    else:
        scan_data["status"] = "down"
    
    if save:
        ensure_scan_dir()
        filename = f"{SCAN_DIR}/nmap_{target.replace('.', '_')}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(scan_data, f, indent=2)
        print(f"[SCAN] Results saved to {filename}")
    
    return scan_data

def nikto_scan(target, save=False):
    """Run Nikto scan and return results."""
    print(f"[SCAN] Running Nikto on {target}...")
    
    # Nikto outputs JSON to a file, not stdout
    stdout, stderr, rc = run_command(
        f"nikto -h {target} -o /tmp/nikto_output.json -Format json"
    )
    
    scan_data = {
        "type": "nikto",
        "target": target,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "findings": []
    }
    
    # Read Nikto JSON output
    if os.path.exists('/tmp/nikto_output.json'):
        try:
            with open('/tmp/nikto_output.json', 'r') as f:
                nikto_data = json.load(f)
            
            # Extract findings
            if isinstance(nikto_data, dict):
                for item in nikto_data.get('Item', []):
                    scan_data["findings"].append({
                        "severity": "high" if "sql" in item.get('Method', '').lower() else "medium",
                        "description": item.get('OSVDB' if 'OSVDB' in item else 'description', 'No description'),
                        "uri": item.get('URI', '/'),
                        "method": item.get('Method', 'GET')
                    })
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    
    if save:
        ensure_scan_dir()
        filename = f"{SCAN_DIR}/nikto_{target.replace('.', '_')}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(scan_data, f, indent=2)
        print(f"[SCAN] Results saved to {filename}")
    
    return scan_data

def analyze_results(scan_data):
    """Analyze scan results using the LLM."""
    if not scan_data:
        print("[ANALYZE] No scan data to analyze.")
        return
    
    prompt = f"""Analyze the following security scan results:

Scan Type: {scan_data.get('type', 'unknown')}
Target: {scan_data.get('target', 'unknown')}
Timestamp: {scan_data.get('timestamp', 'unknown')}
"""
    
    if "findings" in scan_data:
        prompt += f"\nFindings ({len(scan_data['findings'])} total):\n"
        for finding in scan_data["findings"][:10]:
            prompt += f"  - [{finding.get('severity', 'unknown').upper()}] {finding.get('description', 'No description')}\n"
    
    prompt += """
Provide:
1. Executive Summary
2. Critical Findings
3. Recommended Actions
4. Risk Score (1-10)
"""
    
    # Call LLM
    url = f"{LLM_URL}/v1/chat/completions"
    data = json.dumps({
        "model": "Qwen3.6-35B-A3B-GGUF",
        "messages": [
            {"role": "system", "content": "You are a senior security analyst. Provide concise, technical analysis."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response = json.loads(resp.read())
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"\n{'='*60}")
            print(f"  SCAN ANALYSIS REPORT")
            print(f"{'='*60}")
            print(content)
            print(f"{'='*60}")
            return content
    except Exception as e:
        print(f"[ANALYZE] Error: {e}")
        return None

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    target = sys.argv[2]
    save = "--save" in sys.argv
    
    if cmd == "nmap":
        ports = "1-10000"
        if "--ports" in sys.argv:
            idx = sys.argv.index("--ports")
            if idx + 1 < len(sys.argv):
                ports = sys.argv[idx + 1]
        scan_data = nmap_scan(target, ports, save)
        if scan_data:
            analyze_results(scan_data)
    elif cmd == "nikto":
        scan_data = nikto_scan(target, save)
        if scan_data:
            analyze_results(scan_data)
    elif cmd == "full":
        print("[SCAN] Starting full scan...")
        nmap_scan(target, save=True)
        nikto_scan(target, save=True)
        print("[SCAN] Full scan complete.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
