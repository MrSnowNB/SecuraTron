#!/usr/bin/env python3
"""
WebSocket streaming server for SecuraTron SOC.

First-Principles Design:
- WebSockets provide full-duplex communication in a single connection
- LLM streaming uses Server-Sent Events (SSE) format over HTTP
- The bridge: WebSocket client <-> this server <-> LLM SSE stream
- Architecture: asyncio event loop, non-blocking I/O, structured messages

Message Protocol:
  Client -> Server:  {"type": "message", "content": "..."}
  Client <- Server:  {"type": "token", "content": "hello"}
  Client <- Server:  {"type": "reasoning", "content": "..."}
  Client <- Server:  {"type": "complete", "reasoning": "...", "content": "..."}
  Client <- Server:  {"type": "scan_result", "data": {...}}
  Client <- Server:  {"type": "status", "status": "..."}

CRITICAL DISCOVERY: Qwen3.6-35B-A3B-GGUF outputs ALL content to
'reasoning_content' field (NOT 'content'). The 'content' field is always empty.
This code handles both fields for robustness.
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import websockets


# ============================================================
# LLM Streaming Client
# ============================================================

class LLMClient:
    """Streams tokens from Lemonade LLM via SSE."""

    BASE_URL = "http://127.0.0.1:13305"

    def __init__(self):
        self.session_id = None
        self.session_messages = []

    def start_session(self):
        """Start a new chat session on the Lemonade server."""
        try:
            data = json.dumps({}).encode('utf-8')
            req = urllib.request.Request(
                f"{self.BASE_URL}/v1/sessions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                self.session_id = result.get("id")
        except Exception:
            self.session_id = None

    def _build_request(self, message: str, persona: str):
        """Build the request payload and Request object for LLM."""
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a SecuraTron security assistant operating in "
                    f"{persona} mode. Provide concise, actionable security "
                    f"analysis. Format output using markdown when appropriate."
                ),
            },
            {"role": "user", "content": message},
        ]

        payload = {
            "model": "Qwen3.6-35B-A3B-GGUF",
            "messages": messages,
            "max_tokens": 2048,
            "stream": True,
        }

        if self.session_id:
            payload["session_id"] = self.session_id

        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(
            f"{self.BASE_URL}/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        return req

    def _stream_from_response(self, resp):
        """
        Internal helper: iterate over SSE response and yield chunks.
        Qwen3.6-35B-A3B outputs reasoning to 'reasoning_content'
        and final answer to 'content' field. Both must be yielded.
        """
        full_reasoning = ""
        full_content = ""
        token_count = 0

        try:
            buffer = b""
            for raw_line in resp:
                buffer += raw_line
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode('utf-8').strip()

                    if not text.startswith("data: "):
                        continue

                    data_str = text[6:]
                    if data_str == "[DONE]":
                        yield {
                            "type": "complete",
                            "reasoning": full_reasoning,
                            "content": full_content,
                            "token_count": token_count,
                        }
                        return

                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})

                        reasoning_token = delta.get("reasoning_content", "")
                        content_token = delta.get("content", "")

                        if reasoning_token:
                            full_reasoning += reasoning_token
                            yield {
                                "type": "reasoning",
                                "content": reasoning_token,
                            }

                        if content_token:
                            full_content += content_token
                            yield {
                                "type": "token",
                                "content": content_token,
                            }

                        token_count += 1

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e),
                "reasoning": full_reasoning,
                "content": full_content,
            }

    def stream_completion_sync(self, message: str, persona: str = "Analyst"):
        """Synchronous version for HTTP fallback / non-async contexts."""
        req = self._build_request(message, persona)
        with urllib.request.urlopen(req, timeout=300) as resp:
            yield from self._stream_from_response(resp)

    async def stream_completion(self, message: str, persona: str = "Analyst"):
        """
        Async version for WebSocket streaming.

        Uses asyncio.Queue to bridge a synchronous generator (running in
        a background thread) to async iteration. No shared mutable state,
        no race conditions.
        """
        req = self._build_request(message, persona)

        # Open the HTTP response in the calling thread
        import urllib.request
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        # Queue bridges the sync producer to the async consumer.
        # Sentinel value marks end-of-stream.
        import queue
        q: queue.Queue = queue.Queue()

        def _producer():
            try:
                for chunk in self._stream_from_response(resp):
                    q.put(chunk)
            except Exception as e:
                q.put({"type": "error", "error": str(e)})
            finally:
                q.put(None)  # sentinel

        import threading
        t = threading.Thread(target=_producer, daemon=True)
        t.start()

        try:
            while True:
                item = q.get()
                if item is None:  # sentinel → stream done
                    break
                yield item
        finally:
            # Close the urllib response so the thread doesn't block on it
            try:
                resp.close()
            except Exception:
                pass
            t.join(timeout=5)


# ============================================================
# WebSocket Handler
# ============================================================

class WSHandler:
    """Handles WebSocket connections with proper async streaming."""

    def __init__(self):
        self.llm = LLMClient()
        self.active_sessions = {}  # ws -> session info

    def _get_session(self, ws):
        """Get or create a session for this WebSocket connection."""
        if ws not in self.active_sessions:
            self.llm.start_session()
            self.active_sessions[ws] = {
                "created": time.time(),
                "persona": "Analyst",
                "message_count": 0,
            }
        return self.active_sessions[ws]

    async def handle_connection(self, websocket):
        """Main handler for each WebSocket connection."""
        session = self._get_session(websocket)
        persona = session["persona"]

        # Send ready message
        await websocket.send(json.dumps({
            "type": "status",
            "status": "connected",
            "session_id": id(websocket),
            "persona": persona,
        }))

        try:
            async for raw_message in websocket:
                try:
                    msg = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "error": "Invalid JSON",
                    }))
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "message":
                    # Process user message with LLM streaming
                    user_message = msg.get("content", "")
                    if not user_message:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "error": "Empty message",
                        }))
                        continue

                    session["message_count"] += 1
                    persona = msg.get("persona", persona)

                    # Send processing indicator
                    await websocket.send(json.dumps({
                        "type": "status",
                        "status": "processing",
                        "message": "Analysing...",
                    }))

                    # Stream LLM response
                    async for chunk in self.llm.stream_completion(
                        user_message, persona
                    ):
                        await websocket.send(json.dumps(chunk))

                elif msg_type == "set_persona":
                    persona = msg.get("persona", "Analyst")
                    session["persona"] = persona
                    await websocket.send(json.dumps({
                        "type": "status",
                        "status": "persona_changed",
                        "persona": persona,
                    }))

                elif msg_type == "reset_session":
                    self.llm.start_session()
                    session["message_count"] = 0
                    await websocket.send(json.dumps({
                        "type": "status",
                        "status": "session_reset",
                    }))

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "error",
                "error": str(e),
            }))
        finally:
            # Cleanup
            if websocket in self.active_sessions:
                del self.active_sessions[websocket]


# ============================================================
# Simple HTTP Fallback Server
# ============================================================

class HTTPFallbackHandler(BaseHTTPRequestHandler):
    """Provides a simple HTTP fallback for browsers that don't support WebSockets."""

    ws_handler = None  # Set by server

    def do_POST(self):
        """Handle chat messages via HTTP POST (non-streaming fallback)."""
        if self.path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                msg = json.loads(body.decode('utf-8'))

                user_message = msg.get("content", "")
                persona = msg.get("persona", "Analyst")

                # Non-streaming response
                llm_client = LLMClient()
                llm_client.start_session()

                full_response = ""
                full_reasoning = ""
                for chunk in llm_client.stream_completion_sync(
                    user_message, persona
                ):
                    if chunk.get("type") == "token":
                        full_response += chunk.get("content", "")
                    elif chunk.get("type") == "reasoning":
                        full_reasoning += chunk.get("content", "")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = json.dumps({
                    "type": "complete",
                    "content": full_response,
                    "reasoning": full_reasoning,
                })
                self.wfile.write(response.encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress HTTP request logging."""
        pass


def start_http_fallback(port=9998):
    """Start the HTTP fallback server in a background thread."""
    server = HTTPServer(("0.0.0.0", port), HTTPFallbackHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ============================================================
# Main Server
# ============================================================

async def run_ws_server(port=9999):
    """Run the WebSocket streaming server."""
    handler = WSHandler()

    # Also start HTTP fallback
    http_server = start_http_fallback(port=9998)

    async with websockets.serve(handler.handle_connection, "0.0.0.0", port):
        print(f"[ws_stream] WebSocket server running on ws://0.0.0.0:{port}")
        print(f"[ws_stream] HTTP fallback on http://0.0.0.0:{9998}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(run_ws_server())
