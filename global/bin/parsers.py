import xml.etree.ElementTree as ET
import json
import re

PARSERS = {}

def register(type_name):
    def deco(fn):
        PARSERS[type_name] = fn
        return fn
    return deco

@register("shell.run.v1")
def parse_shell_run(raw_stdout, raw_stderr, exit_code, **kwargs):
    return {
        "stdout": raw_stdout,
        "stderr": raw_stderr,
        "exit_code": exit_code,
        "duration_ms": kwargs.get("duration_ms", 0)
    }

@register("fs.read.v1")
def parse_fs_read(raw_stdout, **kwargs):
    return {
        "path": kwargs.get("inputs", {}).get("path", "unknown"),
        "content": raw_stdout,
        "encoding": "utf-8",
        "size": len(raw_stdout.encode("utf-8"))
    }

@register("nmap.scan.v1")
def parse_nmap_scan(raw_stdout, **kwargs):
    """Parse nmap XML output into structured hosts/ports list."""
    try:
        # Nmap -oX - sends XML to stdout
        root = ET.fromstring(raw_stdout)
        hosts = []
        
        for host in root.findall("host"):
            ip = host.find("address").get("addr")
            ports = []
            
            for port in host.findall("ports/port"):
                ports.append({
                    "port": int(port.get("portid")),
                    "protocol": port.get("protocol"),
                    "service": port.find("service").get("name") if port.find("service") is not None else "unknown",
                    "state": port.find("state").get("state")
                })
                
            hosts.append({"ip": ip, "ports": ports})
            
        return {"hosts": hosts}
    except Exception as e:
        return {"error": f"xml_parse_failure: {str(e)}", "raw": raw_stdout[:500]}

@register("whatweb.fingerprint.v1")
def parse_whatweb_fingerprint(raw_stdout, **kwargs):
    """Parse WhatWeb JSON output from stdout."""
    # WhatWeb with --log-json /dev/stdout often appends a brief line after the JSON array
    # We find the JSON array part [...]
    try:
        match = re.search(r"(\[.*\])", raw_stdout, re.DOTALL)
        if not match:
            return {"error": "no_json_array_found", "raw": raw_stdout[:500]}
            
        fingerprints = json.loads(match.group(1))
        
        # Primary result is typically the first entry in the array
        primary = fingerprints[0] if fingerprints else {}
        
        return {
            "fingerprints": fingerprints,
            "status_code": primary.get("http_status"),
            "target": primary.get("target"),
            "raw": raw_stdout
        }
    except Exception as e:
        return {"error": f"json_parse_failure: {str(e)}", "raw": raw_stdout[:500]}

@register("nikto.scan.v1")
def parse_nikto_scan(raw_stdout, **kwargs):
    """Parse nikto JSON output file into structured vulnerability list.
    
    Nikto writes structured JSON to a file (-output), not to stdout.
    The human-readable report goes to stdout. This parser reads the JSON
    file from the expected artifact path and extracts vulnerabilities.
    
    Returns bare dict (the parse() wrapper adds "ok" and "result" keys).
    """
    from pathlib import Path
    
    inputs = kwargs.get("inputs", {})
    session = inputs.get("session", "unknown")
    ts = inputs.get("ts", "unknown")
    
    BASE_DIR = Path.home() / ".securatron"
    
    # Try both naming conventions: nikto-{ts}.json and web.nikto-{ts}.json
    json_path = None
    for base in [
        BASE_DIR / "global" / "sessions",
        BASE_DIR / "sessions",
    ]:
        for candidate in [
            base / session / "artifacts" / f"nikto-{ts}.json",
            base / session / "artifacts" / f"web.nikto-{ts}.json",
        ]:
            if candidate.exists():
                json_path = candidate
                break
        if json_path:
            break
    
    if not json_path:
        # Nikto may fail before creating the artifact (network issues, timeouts)
        # Return a structured error so the dispatch system can classify it
        return {
            "error": "nikto_no_artifact",
            "message": "Nikto did not produce a JSON artifact — likely network or connectivity failure",
            "host": inputs.get("target", "unknown"),
            "searched_paths": [
                str(BASE_DIR / "global" / "sessions" / session / "artifacts" / f"nikto-{ts}.json"),
                str(BASE_DIR / "global" / "sessions" / session / "artifacts" / f"web.nikto-{ts}.json"),
                str(BASE_DIR / "sessions" / session / "artifacts" / f"nikto-{ts}.json"),
                str(BASE_DIR / "sessions" / session / "artifacts" / f"web.nikto-{ts}.json"),
            ],
            "_json_path": None,
        }
    
    with open(json_path) as f:
        content = f.read()
    
    # Handle empty files — nikto may create the file but write nothing
    if not content.strip():
        return {
            "error": "nikto_no_artifact",
            "message": "Nikto created an empty artifact file — target likely unreachable or scan timed out",
            "host": inputs.get("target", "unknown"),
            "_json_path": str(json_path),
        }
    
    data = json.loads(content)
    
    # Nikto JSON format: [{host, ip, port, vulnerabilities: [{id, method, msg, references, url}]}]
    results = []
    total_vulns = 0
    hosts_scanned = set()
    ports_scanned = set()
    
    for scan_result in data:
        host = scan_result.get("host", "unknown")
        ip = scan_result.get("ip", "unknown")
        port = scan_result.get("port", "unknown")
        
        hosts_scanned.add(host)
        ports_scanned.add(port)
        
        vulns = scan_result.get("vulnerabilities", [])
        total_vulns += len(vulns)
        
        for vuln in vulns:
            results.append({
                "vuln_id": str(vuln.get("id")),
                "method": vuln.get("method", "GET"),
                "message": vuln.get("msg", ""),
                "url": vuln.get("url", "/"),
                "references": vuln.get("references", ""),
                "host": host,
                "ip": ip,
                "port": port,
            })
    
    primary = data[0] if data else {}
    
    return {
        "total_findings": total_vulns,
        "hosts_scanned": list(hosts_scanned),
        "ports_scanned": list(ports_scanned),
        "vulnerabilities": results,
        "scan_summary": {
            "host": primary.get("host"),
            "ip": primary.get("ip"),
            "port": primary.get("port"),
            "start_time": primary.get("start_time"),
            "end_time": primary.get("end_time"),
            "server_banner": primary.get("server_banner"),
        },
        "_json_path": str(json_path),
    }

def parse(type_name, raw_stdout, **kwargs):
    """Entry point for parsing raw output into structured data."""
    if type_name not in PARSERS:
        return {"ok": True, "raw": raw_stdout} # Fallback
    
    try:
        parsed = PARSERS[type_name](raw_stdout, **kwargs)
        # If parser returns a dict with 'error' key, treat as failure
        if isinstance(parsed, dict) and "error" in parsed:
            return {"ok": False, "reason": parsed["error"], "result": parsed}
        return {"ok": True, "result": parsed}
    except Exception as e:
        return {"ok": False, "reason": "parsing_exception", "error": str(e)}
