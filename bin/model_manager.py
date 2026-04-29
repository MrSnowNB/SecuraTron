#!/usr/bin/env python3
"""
Securatron Model Manager — backend tool for swapping models on the lemonade server.

Usage:
    python3 model_manager.py status                -- show current model state
    python3 model_manager.py list                  -- list all available models
    python3 model_manager.py load <model_id>       -- load a specific model
    python3 model_manager.py unload                -- unload all models
    python3 model_manager.py swap <model_id>       -- unload current, load new (LLM swap)
    python3 model_manager.py recommend             -- suggest best model for current task

Environment:
    LEMONADE_HOST  -- server host (default: 127.0.0.1)
    LEMONADE_PORT  -- server port (default: 13305)
"""

import json
import sys
import subprocess
import urllib.request
import urllib.error

HOST = "127.0.0.1"
PORT = "13305"

def api(path, method="GET", data=None):
    """Make an API call to the lemonade server."""
    url = f"http://{HOST}:{PORT}{path}"
    req = urllib.request.Request(url, method=method)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body[:200]}")
        sys.exit(1)

def run_cli(*args):
    """Run a lemonade CLI command."""
    result = subprocess.run(
        ["lemonade"] + list(args),
        capture_output=True, text=True, timeout=60
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def status():
    """Show current model status and loaded backends."""
    print("=" * 60)
    print("  LEMONADE SERVER STATUS")
    print("=" * 60)
    h = api("/api/v1/health")
    if not h:
        print("ERROR: server unreachable")
        sys.exit(1)

    print(f"  Version:    {h.get('version', '?')}")
    print(f"  Status:     {h.get('status', '?')}")
    print(f"  Websocket:  port {h.get('websocket_port', '?')}")
    print()

    loaded = h.get("all_models_loaded", [])
    if loaded:
        print(f"  LOADED MODELS ({len(loaded)}):")
        for m in loaded:
            dev = m.get("device", "?")
            port = m.get("backend_url", "?").split(":")[-1].rstrip("/v1")
            recipe = m.get("recipe", "?")
            ckpt = m.get("checkpoint", "?").split(":")[-1][:35]
            mtype = m.get("type", "?")
            print(f"    [{mtype:>5}] {m.get('model_name','?'):30s}  {dev:>4}  :{port:>4}  ({ckpt})")
    else:
        print("  LOADED MODELS: none")

    print()
    models = api("/v1/models")
    if models:
        loaded_names = {m["model_name"] for m in loaded}
        unloaded = [m for m in models["data"] if m["id"] not in loaded_names]
        if unloaded:
            print(f"  AVAILABLE BUT UNLOADED ({len(unloaded)}):")
            for m in unloaded:
                size = m.get("size", "?")
                labels = ", ".join(m.get("labels", [])[:3])
                print(f"    [{labels:>20}] {m['id']:30s}  {size:>5}GB  ({m.get('recipe','?')})")

    print("=" * 60)

def list_models():
    """List all available models with details."""
    models = api("/v1/models")
    if not models:
        print("No models available")
        return

    h = api("/api/v1/health")
    loaded_names = {m["model_name"] for m in h.get("all_models_loaded", [])}

    print(f"{'ID':<35} {'Recipe':<10} {'Size':>5} {'Device':>6} {'Labels':<25} {'Status':<8}")
    print("-" * 95)
    for m in models["data"]:
        mid = m["id"]
        recipe = m.get("recipe", "?")
        size = m.get("size", "?")
        labels = ", ".join(m.get("labels", [])[:2])
        loaded = "LOADED" if mid in loaded_names else ""

        device = "?"
        for lm in h.get("all_models_loaded", []):
            if lm["model_name"] == mid:
                device = lm.get("device", "?")
                break
        if device == "?" and m.get("recipe") in ("sd-cpp",):
            device = "gpu"

        print(f"{mid:<35} {recipe:<10} {size:>5}    {device:>6} {labels:<25} {loaded:<8}")

def load_model(model_id):
    """Load a specific model via CLI."""
    out, err, rc = run_cli("load", model_id)
    print(out or err)
    import time; time.sleep(2)
    status()

def unload_model(model_id=None):
    """Unload models via CLI."""
    if model_id:
        out, err, rc = run_cli("unload", model_id)
        print(out or err)
    else:
        out, err, rc = run_cli("unload")
        print(out or err)
    import time; time.sleep(1)
    status()

def swap_model(model_id):
    """Swap to a different LLM model — unload current LLM only, load new one."""
    # Get current LLM
    h = api("/api/v1/health")
    current_llm = [m for m in h.get("all_models_loaded", []) if m.get("type") == "llm"]
    if current_llm:
        print(f"Unloading current LLM: {current_llm[0]['model_name']}...")
        out, err, rc = run_cli("unload", current_llm[0]["model_name"])
        print(out or err)
        import time; time.sleep(5)
    else:
        print("No current LLM to unload")

    print(f"Loading model: {model_id}...")
    out, err, rc = run_cli("load", model_id)
    print(out or err)
    import time; time.sleep(10)
    status()
    # Test chat with new model
    test_chat(model_id)

def test_chat(model_id):
    """Quick chat test with the newly loaded model."""
    import urllib.request
    url = f"http://{HOST}:{PORT}/v1/chat/completions"
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "Say 'hello from the new model'"}],
        "max_tokens": 30
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if reply:
                print(f"\n  TEST RESPONSE: {reply[:100]}")
            else:
                reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
                if reasoning:
                    print(f"\n  MODEL THINKING: {reasoning[:100]}...")
    except Exception as e:
        print(f"\n  Chat test failed: {e}")

def recommend():
    """Suggest the best model based on current system state."""
    h = api("/api/v1/health")
    models = api("/v1/models")

    import psutil
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024**3)
    avail_gb = mem.available / (1024**3)
    used_gb = mem.used / (1024**3)

    print(f"System: {total_gb:.0f}GB RAM ({used_gb:.0f}GB used, {avail_gb:.0f}GB available)")
    print()

    current = h.get("all_models_loaded", [])
    current_llm = [m for m in current if m.get("type") == "llm"]

    llms = [m for m in models["data"] if m.get("recipe") == "llamacpp"]
    llms.sort(key=lambda m: m.get("size", 999))

    print("Recommendations:")
    for m in llms:
        size = m.get("size", 999)
        labels = m.get("labels", [])
        loaded = m["id"] in {lm["model_name"] for lm in current}
        fits = size < avail_gb * 0.8

        status_str = "LOADED" if loaded else ("FITS" if fits else "TOO LARGE")
        extras = ", ".join(labels[:2])
        print(f"  {m['id']:35s}  {size:>5.1f}GB  [{status_str:>9}]  ({extras})")

    if current_llm:
        print(f"\n  Current: {current_llm[0]['model_name']}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "status":
        status()
    elif cmd == "list":
        list_models()
    elif cmd == "load":
        if len(sys.argv) < 3:
            print("Usage: model_manager.py load <model_id>")
            sys.exit(1)
        load_model(sys.argv[2])
    elif cmd == "unload":
        model_id = sys.argv[2] if len(sys.argv) > 2 else None
        unload_model(model_id)
    elif cmd == "swap":
        if len(sys.argv) < 3:
            print("Usage: model_manager.py swap <model_id>")
            sys.exit(1)
        swap_model(sys.argv[2])
    elif cmd == "recommend":
        recommend()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
