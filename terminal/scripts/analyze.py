#!/usr/bin/env python3
"""
Securatron Threat Analysis Engine
First Principles Architecture — Analysis Layer

Usage:
    python3 analyze.py scan <file>       -- Analyze scan results
    python3 analyze.py threat <text>     -- Analyze threat report
    python3 analyze.py surface <target>  -- Analyze attack surface
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

LLM_URL = "http://localhost:13305"

def api_call(endpoint, data=None, method="POST"):
    """Make an API call to the lemonade server."""
    url = f"{LLM_URL}{endpoint}"
    req = urllib.request.Request(url, method=method)
    if data is not None:
        if isinstance(data, dict):
            req.data = json.dumps(data).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        else:
            req.data = data.encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return None

def analyze_scan(scan_file):
    """Analyze scan results from a file."""
    try:
        with open(scan_file, 'r') as f:
            scan_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {scan_file}: {e}")
        return
    
    # Build analysis prompt
    prompt = f"""Analyze the following security scan results and provide a comprehensive threat assessment:

Scan Type: {scan_data.get('type', 'unknown')}
Target: {scan_data.get('target', 'unknown')}
Timestamp: {scan_data.get('timestamp', 'unknown')}

Findings ({len(scan_data.get('findings', []))} total):
"""
    for finding in scan_data.get('findings', [])[:20]:
        prompt += f"  - {finding.get('severity', 'unknown').upper()}: {finding.get('description', 'No description')}\n"
    
    prompt += """
Please provide:
1. Executive Summary (2-3 sentences)
2. Critical Findings (top 3)
3. Recommended Actions (prioritized)
4. Risk Score (1-10)
"""
    
    # Call LLM
    response = api_call("/v1/chat/completions", {
        "model": "Qwen3.6-35B-A3B-GGUF",
        "messages": [
            {"role": "system", "content": "You are a senior security analyst. Provide concise, technical, and actionable analysis."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    })
    
    if response:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"\n{'='*60}")
        print(f"  THREAT ANALYSIS REPORT")
        print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        print(content)
        print(f"{'='*60}")
        return content
    return None

def analyze_threat(threat_text):
    """Analyze a threat report."""
    prompt = f"""Analyze the following threat intelligence and provide actionable insights:

{threat_text}

Please provide:
1. Threat Classification
2. Severity Assessment
3. Attack Vector Analysis
4. Mitigation Recommendations
5. Indicators of Compromise (IOCs)
"""
    
    response = api_call("/v1/chat/completions", {
        "model": "Qwen3.6-35B-A3B-GGUF",
        "messages": [
            {"role": "system", "content": "You are a threat intelligence analyst. Provide concise, technical analysis."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    })
    
    if response:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"\n{content}")
        return content
    return None

def analyze_surface(target):
    """Analyze attack surface for a target."""
    prompt = f"""Analyze the attack surface for target: {target}

Provide:
1. External Attack Surface (IPs, domains, services)
2. Internal Attack Surface (if applicable)
3. Common Vulnerabilities for this target type
4. Recommended Scanning Strategy
5. Risk Prioritization
"""
    
    response = api_call("/v1/chat/completions", {
        "model": "Qwen3.6-35B-A3B-GGUF",
        "messages": [
            {"role": "system", "content": "You are a security architect. Provide comprehensive attack surface analysis."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.7
    })
    
    if response:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"\n{content}")
        return content
    return None

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == "scan" and len(sys.argv) >= 3:
        analyze_scan(sys.argv[2])
    elif cmd == "threat" and len(sys.argv) >= 3:
        analyze_threat(" ".join(sys.argv[2:]))
    elif cmd == "surface" and len(sys.argv) >= 3:
        analyze_surface(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
