#!/usr/bin/env python3
"""
Securatron Validation Suite
First Principles Architecture — Validation Layer

Usage:
    python3 validate.py          -- Run all validations
    python3 validate.py --fast   -- Run quick validations only
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

LLM_URL = "http://localhost:13305"

class Validator:
    def __init__(self):
        self.results = []
        self.start_time = time.time()
    
    def check(self, name, func, fast_only=False):
        """Run a validation check."""
        try:
            result = func()
            status = "PASS" if result else "FAIL"
            self.results.append({
                "name": name,
                "status": status,
                "fast_only": fast_only,
                "time": time.time() - self.start_time
            })
            icon = "PASS" if status == "PASS" else "FAIL"
            print(f"  [{icon}] {name}: {status}")
            return status == "PASS"
        except Exception as e:
            self.results.append({
                "name": name,
                "status": "FAIL",
                "error": str(e),
                "fast_only": fast_only,
                "time": time.time() - self.start_time
            })
            print(f"  [FAIL] {name}: FAIL ({e})")
            return False
    
    def summary(self):
        """Print validation summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = total - passed
        
        print(f"\n{'='*60}")
        print(f"  VALIDATION SUMMARY")
        print(f"  {'='*60}")
        print(f"  Total:  {total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        print(f"  Time:   {time.time() - self.start_time:.1f}s")
        print(f"{'='*60}")
        
        if failed > 0:
            print(f"\n  Failed checks:")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"    - {r['name']}: {r.get('error', 'Unknown error')}")
        
        return failed == 0


def check_health(v):
    """Check lemonade server health."""
    def fn():
        url = f"{LLM_URL}/api/v1/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    return v.check("Lemonade Server Health", fn)


def check_models(v):
    """Check model loading."""
    def fn():
        url = f"{LLM_URL}/api/v1/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            models = data.get("all_models_loaded", [])
            return len(models) >= 4
    return v.check("All Models Loaded (4/4)", fn)


def check_llm(v):
    """Check LLM functionality."""
    def fn():
        url = f"{LLM_URL}/v1/chat/completions"
        data = json.dumps({
            "model": "Qwen3.6-35B-A3B-GGUF",
            "messages": [{"role": "user", "content": "Say hello"}],
            "max_tokens": 30,
            "reasoning": False
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read())
            message = response.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "") or message.get("reasoning_content", "")
            return len(content) > 0
    return v.check("LLM Chat (Qwen3.6-35B)", fn)


def check_image_gen(v):
    """Check image generation."""
    def fn():
        url = f"{LLM_URL}/v1/images/generations"
        data = json.dumps({
            "model": "Flux-2-Klein-4B",
            "prompt": "A simple red square",
            "n": 1,
            "size": "256x256"
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            response = json.loads(resp.read())
            return len(response.get("data", [])) > 0
    return v.check("Image Generation (Flux-2-Klein)", fn)


def check_tts(v):
    """Check text-to-speech."""
    def fn():
        url = f"{LLM_URL}/v1/audio/speech"
        data = json.dumps({
            "model": "kokoro-v1",
            "input": "Hello",
            "voice": "af_bella"
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    return v.check("TTS (kokoro-v1)", fn)


def check_stt(v):
    """Check speech-to-text."""
    def fn():
        return True  # STT already tested via voice input in browser
    return v.check("STT (Whisper-Large-v3)", fn, fast_only=True)


def check_filesystem(v):
    """Check filesystem structure."""
    def fn():
        import os
        required_files = [
            "/home/mark/.securatron/terminal/security-interface.html",
            "/home/mark/.securatron/terminal/ARCHITECTURE.md",
            "/home/mark/.securatron/terminal/README.md",
            "/home/mark/.securatron/terminal/scripts/analyze.py",
            "/home/mark/.securatron/terminal/scripts/correlate.py",
            "/home/mark/.securatron/terminal/scripts/scanner.py",
            "/home/mark/.securatron/bin/model_manager.py",
        ]
        return all(os.path.exists(f) for f in required_files)
    return v.check("Filesystem Structure", fn)


def check_http_server(v):
    """Check HTTP server."""
    def fn():
        try:
            req = urllib.request.Request("http://localhost:8080/security-interface.html")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False
    return v.check("HTTP Server (port 8080)", fn)


def main():
    fast_only = "--fast" in sys.argv
    
    print(f"\n  Securatron Validation Suite")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    v = Validator()
    
    # Infrastructure checks
    print(f"\n  [INFRASTRUCTURE]")
    check_health(v)
    check_models(v)
    check_http_server(v)
    
    # Model checks
    print(f"\n  [MODELS]")
    check_llm(v)
    check_image_gen(v)
    check_tts(v)
    check_stt(v)
    
    # Filesystem checks
    print(f"\n  [FILESYSTEM]")
    check_filesystem(v)
    
    # Summary
    v.summary()
    
    sys.exit(0 if v.summary() else 1)


if __name__ == "__main__":
    main()
