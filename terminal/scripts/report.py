#!/usr/bin/env python3
"""
Securatron Report Generator
First Principles Architecture — Reporting Layer

Usage:
    python3 report.py generate <target>  -- Generate security report
    python3 report.py summary <file>     -- Generate executive summary
"""

import json
import sys
import urllib.request

LLM_URL = "http://localhost:13305"

def generate_report(target):
    """Generate a comprehensive security report."""
    prompt = f"""Generate a comprehensive security assessment report for target: {target}

Include:
1. Executive Summary
2. Scope of Assessment
3. Methodology
4. Findings (Critical, High, Medium, Low)
5. Risk Assessment
6. Recommendations
7. Appendix (Tools used, References)

Format as a professional security report."""
    
    response = call_llm(prompt)
    if response:
        print(f"\n{'='*60}")
        print(f"  SECURITY ASSESSMENT REPORT")
        print(f"  Target: {target}")
        print(f"  Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(response)
        print(f"{'='*60}")
        return response
    return None

def generate_summary(scan_file):
    """Generate an executive summary from scan results."""
    try:
        with open(scan_file, 'r') as f:
            scan_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {scan_file}: {e}")
        return
    
    prompt = f"""Generate an executive summary for the following security scan:

Scan Type: {scan_data.get('type', 'unknown')}
Target: {scan_data.get('target', 'unknown')}
Findings: {len(scan_data.get('findings', []))} total

Provide a concise executive summary suitable for leadership."""
    
    response = call_llm(prompt)
    if response:
        print(f"\n{response}")
        return response
    return None

def call_llm(prompt):
    """Call the LLM via the lemonade server."""
    url = f"{LLM_URL}/v1/chat/completions"
    data = json.dumps({
        "model": "Qwen3.6-35B-A3B-GGUF",
        "messages": [
            {"role": "system", "content": "You are a senior security consultant. Provide professional, well-structured reports."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4096,
        "temperature": 0.7
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response = json.loads(resp.read())
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == "generate" and len(sys.argv) >= 3:
        generate_report(sys.argv[2])
    elif cmd == "summary" and len(sys.argv) >= 3:
        generate_summary(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
