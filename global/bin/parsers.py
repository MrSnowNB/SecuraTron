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
        all_ports = {}  # port_num -> bool (open/closed)
        port_open_flags = {}  # e.g. port_22_open: True
        
        for host in root.findall("host"):
            ip = host.find("address").get("addr")
            ports = []
            
            for port in host.findall("ports/port"):
                port_num = int(port.get("portid"))
                state = port.find("state").get("state") if port.find("state") is not None else "closed"
                ports.append({
                    "port": port_num,
                    "protocol": port.get("protocol"),
                    "service": port.find("service").get("name") if port.find("service") is not None else "unknown",
                    "state": state
                })
                # Track open status for condition gates
                all_ports[port_num] = (state == "open")
                # Create top-level boolean flags for common ports
                port_open_flags[f"port_{port_num}_open"] = (state == "open")
                
            hosts.append({"ip": ip, "ports": ports})
        
        return {"hosts": hosts, "ports": all_ports, **port_open_flags}
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


@register("web.browser.drill.v1")
def parse_browser_drill(raw_stdout, **kwargs):
    """Parse browser_drill.py JSON output into structured element details."""
    try:
        data = json.loads(raw_stdout)
        if data.get("error") or not data.get("found"):
            return {"error": data.get("error", "element_not_found"), "raw": raw_stdout[:500]}
        
        return {
            "page_id": data.get("page_id"),
            "url": data.get("url"),
            "selector": data.get("selector"),
            "resolved_selector": data.get("resolved_selector"),
            "element": {
                "tag": data.get("element", {}).get("tag"),
                "text": data.get("element", {}).get("text"),
                "attributes": data.get("element", {}).get("attributes", {}),
                "computed_style": data.get("element", {}).get("computed_style", {}),
                "events": data.get("element", {}).get("events", []),
                "parent_context": data.get("element", {}).get("parent_context", []),
                "form_context": data.get("element", {}).get("form_context"),
                "aria": data.get("element", {}).get("aria", {})
            }
        }
    except json.JSONDecodeError as e:
        return {"error": f"json_parse_failure: {str(e)}", "raw": raw_stdout[:500]}


@register("web.browser.interact.v1")
def parse_browser_interact(raw_stdout, **kwargs):
    """Parse browser_interact.py JSON output into structured interaction result."""
    try:
        data = json.loads(raw_stdout)
        return {
            "page_id": data.get("page_id"),
            "url": data.get("url"),
            "action_performed": data.get("action_performed"),
            "selector": data.get("selector"),
            "success": data.get("success"),
            "element_state": data.get("element_state", {}),
            "result": {
                "new_url": data.get("result", {}).get("new_url"),
                "url_changed": data.get("result", {}).get("url_changed"),
                "new_title": data.get("result", {}).get("new_title"),
                "new_page_summary": data.get("result", {}).get("new_page_summary"),
                "new_interactive_count": data.get("result", {}).get("new_interactive_count"),
                "alert_triggered": data.get("result", {}).get("alert_triggered"),
                "alert_message": data.get("result", {}).get("alert_message"),
                "errors": data.get("result", {}).get("errors", [])
            }
        }
    except json.JSONDecodeError as e:
        return {"error": f"json_parse_failure: {str(e)}", "raw": raw_stdout[:500]}


@register("exploit.search.v1")
def parse_exploit_search(raw_stdout, **kwargs):
    """Parse searchsploit output into structured CVE/exploit list."""
    results = []
    
    for line in raw_stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("["):
            continue
        
        # searchsploit output format:
        # Exploit: Apache HTTP Server 2.4.49 Path Traversal
        # UID: 50230
        # UID: ...
        # RID: 49642
        # Updated: 2021-12-15
        # CVE: CVE-2021-41773
        # CVSS: 7.5
        # ...
        # Path: /usr/share/exploitdb/exploits/linux/remote/50230.py
        # ...
        
        # Each entry starts with "Exploit:" or is a blank line between entries
        if line.startswith("Exploit:") or (line and not any(line.startswith(k) for k in ["UID:", "RID:", "Updated:", "CVE:", "CVSS:", "Path:", "Platform:", "Type:", "Download:"])):
            current = {"title": line.replace("Exploit:", "").strip(), "uid": [], "rid": [], "cve": [], "path": "", "platform": "", "type": "", "download_url": ""}
        elif line.startswith("UID:"):
            current.setdefault("uid", []).append(line.replace("UID:", "").strip())
        elif line.startswith("RID:"):
            current.setdefault("rid", []).append(line.replace("RID:", "").strip())
        elif line.startswith("CVE:"):
            current.setdefault("cve", []).append(line.replace("CVE:", "").strip())
        elif line.startswith("Path:"):
            current["path"] = line.replace("Path:", "").strip()
        elif line.startswith("Platform:"):
            current["platform"] = line.replace("Platform:", "").strip()
        elif line.startswith("Type:"):
            current["type"] = line.replace("Type:", "").strip()
        elif line.startswith("Download:"):
            current["download_url"] = line.replace("Download:", "").strip()
        elif line.strip() and not current:
            # Single-line format: "Exploit Title | UID | Platform"
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                current = {"title": parts[0], "uid": [parts[1]], "cve": [], "path": "", "platform": parts[2] if len(parts) > 2 else "", "type": "", "download_url": ""}
        
        if "title" in locals():
            results.append(current)
            current = None
    
    # Handle single-line format entries that may not have been captured
    if not results:
        for line in raw_stdout.strip().split("\n"):
            line = line.strip()
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    results.append({
                        "title": parts[0],
                        "uid": [parts[1]] if len(parts) > 1 else [],
                        "cve": [],
                        "path": "",
                        "platform": parts[2] if len(parts) > 2 else "",
                        "type": "",
                        "download_url": ""
                    })
    
    return {
        "total_matches": len(results),
        "exploits": results[:50]  # Cap at 50 to match head -50
    }


@register("post.exploit.recon.v1")
def parse_post_exploit_recon(raw_stdout, **kwargs):
    """Parse multi-section recon output into categorized structured data."""
    sections = {
        "identity": {},
        "sudo": [],
        "suid_binaries": [],
        "credentials": [],
        "recent_files": [],
        "crontabs": [],
        "environment": [],
        "network": [],
        "capabilities": [],
        "docker": [],
        "kernel": {}
    }
    
    current_section = None
    current_lines = []
    
    for line in raw_stdout.split("\n"):
        # Detect section headers
        if "--- IDENTITY ---" in line:
            current_section = "identity"
            current_lines = []
        elif "--- SUDO ---" in line:
            current_section = "sudo"
            current_lines = []
        elif "--- SUID BINARIES ---" in line:
            current_section = "suid_binaries"
            current_lines = []
        elif "--- CREDENTIALS ---" in line:
            current_section = "credentials"
            current_lines = []
        elif "--- RECENT FILES ---" in line:
            current_section = "recent_files"
            current_lines = []
        elif "--- CRONTABS ---" in line:
            current_section = "crontabs"
            current_lines = []
        elif "--- ENVIRONMENT ---" in line:
            current_section = "environment"
            current_lines = []
        elif "--- NETWORK ---" in line:
            current_section = "network"
            current_lines = []
        elif "--- CAPABILITIES ---" in line:
            current_section = "capabilities"
            current_lines = []
        elif "--- DOCKER ---" in line:
            current_section = "docker"
            current_lines = []
        elif "--- KERNEL ---" in line:
            current_section = "kernel"
            current_lines = []
        elif current_section and line.strip():
            current_lines.append(line)
    
    # Process each section
    if current_section == "identity" and "current_lines" in locals():
        sections["identity"] = {"raw": current_lines}
    elif current_section == "sudo" and "current_lines" in locals():
        sections["sudo"] = [l for l in current_lines if l.strip()]
    elif current_section == "suid_binaries" and "current_lines" in locals():
        sections["suid_binaries"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "credentials" and "current_lines" in locals():
        sections["credentials"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "recent_files" and "current_lines" in locals():
        sections["recent_files"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "crontabs" and "current_lines" in locals():
        sections["crontabs"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "environment" and "current_lines" in locals():
        sections["environment"] = [l.strip() for l in current_lines if l.strip() and "=" in l]
    elif current_section == "network" and "current_lines" in locals():
        sections["network"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "capabilities" and "current_lines" in locals():
        sections["capabilities"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "docker" and "current_lines" in locals():
        sections["docker"] = [l.strip() for l in current_lines if l.strip()]
    elif current_section == "kernel" and "current_lines" in locals():
        sections["kernel"] = {"raw": current_lines}
    
    # Identify privilege escalation vectors
    privesc_vectors = []
    
    # Check for sudo without password
    for line in sections["sudo"]:
        if "(ALL) NOPASSWD:" in line or "NOPASSWD:" in line:
            privesc_vectors.append({
                "type": "sudo_nopasswd",
                "detail": line.strip()
            })
    
    # Check for SUID binaries
    if sections["suid_binaries"]:
        known_suid_privesc = ["sudo", "vim", "vi", "nmap", "find", "bash", "sh", "python", "python3", "perl", "ruby", "lua", "awk", "sed", "git", "docker", "tar"]
        for binary in sections["suid_binaries"]:
            for known in known_suid_privesc:
                if known in binary.lower():
                    privesc_vectors.append({
                        "type": "suid_binary",
                        "binary": binary.strip(),
                        "risk": "high" if known in ["sudo", "docker", "vim", "nmap", "find"] else "medium"
                    })
    
    # Check for world-writable files
    if sections["recent_files"]:
        for f in sections["recent_files"]:
            if any(kw in f.lower() for kw in [".key", ".pem", "passwd", "shadow"]):
                privesc_vectors.append({
                    "type": "sensitive_file",
                    "file": f.strip()
                })
    
    return {
        "sections": sections,
        "privesc_vectors": privesc_vectors,
        "total_sections": len([k for k, v in sections.items() if v])
    }


@register("web.browser.inspect.v1")
def parse_browser_inspect(raw_stdout, **kwargs):
    """Parse browser_inspect.py JSON output into structured page analysis."""
    try:
        data = json.loads(raw_stdout)
        if data.get("error"):
            return {"ok": False, "reason": data["error"], "raw": raw_stdout[:500]}
        
        elements = data.get("interactive_elements", [])
        return {
            "page_id": data.get("page_id"),
            "url": data.get("url"),
            "title": data.get("title"),
            "structure": data.get("structure", []),
            "interactive_count": data.get("interactive_count", 0),
            "summary": data.get("summary", ""),
            "elements": [
                {
                    "ref_id": e.get("ref_id"),
                    "tag": e.get("tag"),
                    "text": e.get("text", ""),
                    "type": e.get("type"),
                    "position": e.get("position"),
                    "meta": e.get("meta", {})
                }
                for e in elements
            ],
            "has_forms": any(e.get("meta", {}).get("input_type") for e in elements),
            "has_buttons": any(e.get("tag") == "button" for e in elements),
            "has_links": any(e.get("tag") == "a" for e in elements)
        }
    except json.JSONDecodeError as e:
        return {"ok": False, "reason": "json_parse_failure", "error": str(e), "raw": raw_stdout[:500]}


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
