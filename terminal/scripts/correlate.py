#!/usr/bin/env python3
"""
Securatron Threat Correlation Engine
First Principles Architecture — Correlation Layer

Usage:
    python3 correlate.py events <file>  -- Correlate security events
    python3 correlate.py patterns       -- Detect attack patterns
"""

import json
import sys
from datetime import datetime, timedelta

def correlate_events(events_file):
    """Correlate security events from a file."""
    try:
        with open(events_file, 'r') as f:
            events = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {events_file}: {e}")
        return
    
    # Group events by source IP
    ip_events = {}
    for event in events:
        src_ip = event.get('source_ip', 'unknown')
        if src_ip not in ip_events:
            ip_events[src_ip] = []
        ip_events[src_ip].append(event)
    
    # Find correlated attacks
    print(f"\n{'='*60}")
    print(f"  THREAT CORRELATION REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    for ip, evts in ip_events.items():
        if len(evts) >= 3:  # Multiple events from same IP = correlated
            print(f"\n[!] Correlated Activity: {ip}")
            print(f"    Events: {len(evts)}")
            types = set(e.get('type', 'unknown') for e in evts)
            print(f"    Types: {', '.join(types)}")
            print(f"    Timeline: {evts[0].get('timestamp', '?')} to {evts[-1].get('timestamp', '?')}")
    
    print(f"\n{'='*60}")

def detect_patterns(events):
    """Detect common attack patterns."""
    # Define common patterns
    patterns = {
        'port_scan': {'type': 'port_scan', 'min_count': 5},
        'brute_force': {'type': 'auth_failure', 'min_count': 3},
        'sql_injection': {'pattern': 'SQL injection', 'min_count': 1},
        'xss_attack': {'pattern': 'XSS', 'min_count': 1},
    }
    
    print(f"\n{'='*60}")
    print(f"  ATTACK PATTERN DETECTION")
    print(f"{'='*60}")
    
    for pattern_name, pattern_def in patterns.items():
        count = 0
        for event in events:
            if pattern_def.get('type') and event.get('type') == pattern_def['type']:
                count += 1
            elif pattern_def.get('pattern') and pattern_def['pattern'].lower() in event.get('description', '').lower():
                count += 1
        
        if count >= pattern_def.get('min_count', 1):
            print(f"\n[!] {pattern_name.upper()} DETECTED")
            print(f"    Occurrences: {count}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == "events" and len(sys.argv) >= 3:
        correlate_events(sys.argv[2])
    elif cmd == "patterns":
        # Read from stdin or file
        if len(sys.argv) >= 3:
            with open(sys.argv[2], 'r') as f:
                events = json.load(f)
        else:
            events = json.loads(sys.stdin.read())
        detect_patterns(events)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
