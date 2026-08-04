#!/usr/bin/env python3
"""
swarm/ws_server.py — WebSocket progress server for the swarm.

Streams live swarm run events to connected browsers in real-time.
Uses only stdlib (http.server + websockets via simple WS frame implementation).

Architecture:
- The swarm writes to a memory.jsonl file (already does this)
- This server tails the file and broadcasts new lines to all connected clients
- Clients connect via ws://localhost:8765/ and receive JSON events

No external dependencies. No asyncio. Single-threaded.

Usage:
    python3 swarm/ws_server.py --memory-dir /tmp/swarm-state/run-123 --port 8765

    # In a browser:
    # const ws = new WebSocket('ws://localhost:8765/');
    # ws.onmessage = (e) => console.log(JSON.parse(e.data));
"""

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


# ============================================================================
# Minimal WebSocket frame implementation (RFC 6455)
# ============================================================================

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_encode_frame(payload: bytes) -> bytes:
    """Encode a WebSocket text/binary frame (server → client, no masking)."""
    if len(payload) <= 125:
        header = bytes([0x81])  # FIN + text opcode
        header += bytes([0x80 | len(payload)])  # MASK=0, length
    elif len(payload) <= 65535:
        header = bytes([0x81, 0x80 | 126]) + len(payload).to_bytes(2, "big")
    else:
        header = bytes([0x81, 0x80 | 127]) + len(payload).to_bytes(8, "big")
    return header + payload


def ws_decode_frame(stream: bytes, offset: int = 0) -> tuple[bytes, int]:
    """Decode one client → server frame. Returns (payload, new_offset)."""
    if len(stream) < offset + 2:
        return b"", offset
    b1, b2 = stream[offset], stream[offset + 1]
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    length = b2 & 0x7F
    pos = offset + 2

    if length == 126:
        if len(stream) < pos + 2: return b"", offset
        length = int.from_bytes(stream[pos:pos + 2], "big")
        pos += 2
    elif length == 127:
        if len(stream) < pos + 8: return b"", offset
        length = int.from_bytes(stream[pos:pos + 8], "big")
        pos += 8

    if masked:
        if len(stream) < pos + 4: return b"", offset
        mask = stream[pos:pos + 4]
        pos += 4
    else:
        mask = None

    if len(stream) < pos + length:
        return b"", offset

    payload = stream[pos:pos + length]
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

    return payload, pos + length


def ws_handshake(key: str) -> str:
    """Compute Sec-WebSocket-Accept from client's Sec-WebSocket-Key."""
    import hashlib
    import base64
    digest = hashlib.sha1((key + WS_GUID).encode()).digest()
    return base64.b64encode(digest).decode()


# ============================================================================
# Server
# ============================================================================

class SwarmWebSocketServer:
    """Streams memory.jsonl events to all connected WebSocket clients."""

    def __init__(self, memory_dir: Path, host: str = "localhost", port: int = 8765):
        self.memory_dir = Path(memory_dir)
        self.host = host
        self.port = port
        self.clients: set = set()  # active websocket connections (dict {client: dict})
        self.lock = threading.Lock()
        self.last_sent_index = 0
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.stats = {
            "connected_clients": 0,
            "events_sent": 0,
            "started_at": None,
        }

    def start(self):
        """Start the file-tail thread + HTTP server."""
        self.stats["started_at"] = datetime.now(timezone.utc).isoformat()
        self.running = True
        self.thread = threading.Thread(target=self._tail_loop, daemon=True)
        self.thread.start()
        self._serve()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _tail_loop(self):
        """Tail memory.jsonl and broadcast new lines."""
        log_path = self.memory_dir / "memory.jsonl"
        while self.running:
            try:
                if log_path.exists():
                    with open(log_path) as f:
                        # Read all new lines since last index
                        lines = f.readlines()
                        new_lines = lines[self.last_sent_index:]
                        for line in new_lines:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                event = json.loads(line)
                                self._broadcast(event)
                                self.last_sent_index += 1
                                self.stats["events_sent"] += 1
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                print(f"Tail error: {e}", file=sys.stderr)
            time.sleep(0.2)

    def _broadcast(self, event: dict):
        """Send an event to all connected clients."""
        msg = json.dumps(event).encode()
        frame = ws_encode_frame(msg)
        dead = set()
        with self.lock:
            for client_data in self.clients:
                try:
                    client_data["sock"].sendall(frame)
                except Exception:
                    dead.add(client_data)
            self.clients -= dead
        self.stats["connected_clients"] = len(self.clients)

    def _serve(self):
        """Run the HTTP+WebSocket server (blocking)."""
        server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        print(f"✓ Swarm WS server: ws://{self.host}:{self.port}/")
        print(f"  Memory dir: {self.memory_dir}")
        print(f"  Log file: {self.memory_dir}/memory.jsonl")
        print()
        print("  Connect with:")
        print(f"    wscat -c ws://{self.host}:{self.port}")
        print(f"  Or open swarm/dashboard.html in a browser")
        print()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            server.shutdown()

    def _make_handler(self):
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Suppress default logging
                pass

            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_ref.stats).encode())
                    return
                if self.path == "/" or self.path == "/ws":
                    self._handle_websocket()
                    return
                if self.path == "/events":
                    # Replay all events as JSON (for late-joining clients)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    log_path = server_ref.memory_dir / "memory.jsonl"
                    events = []
                    if log_path.exists():
                        with open(log_path) as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try: events.append(json.loads(line))
                                    except: pass
                    self.wfile.write(json.dumps(events).encode())
                    return
                # Serve dashboard.html
                if self.path == "/dashboard" or self.path == "/dashboard.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    html = server_ref._render_dashboard_html()
                    self.wfile.write(html.encode())
                    return
                self.send_response(404)
                self.end_headers()

            def _handle_websocket(self):
                # WebSocket upgrade handshake
                upgrade = self.headers.get("Upgrade", "")
                if upgrade.lower() != "websocket":
                    self.send_response(400)
                    self.end_headers()
                    return
                key = self.headers.get("Sec-WebSocket-Key", "")
                if not key:
                    self.send_response(400)
                    self.end_headers()
                    return
                accept = ws_handshake(key)
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()

                # Register client
                client = {"sock": self.connection, "addr": self.client_address}
                with server_ref.lock:
                    server_ref.clients.add(client)
                server_ref.stats["connected_clients"] = len(server_ref.clients)
                print(f"  + Client connected: {self.client_address} "
                      f"(total: {server_ref.stats['connected_clients']})")

                # Read loop (handle pings + close)
                buf = b""
                try:
                    while server_ref.running:
                        try:
                            chunk = self.connection.recv(4096)
                        except Exception:
                            break
                        if not chunk:
                            break
                        buf += chunk
                        # Decode any frames in buffer
                        while True:
                            payload, new_pos = ws_decode_frame(buf, 0)
                            if not payload and new_pos == 0:
                                break
                            buf = buf[new_pos:]
                            # We don't expect client → server messages
                            # (could add ping/pong handling here)
                finally:
                    with server_ref.lock:
                        server_ref.clients.discard(client)
                    server_ref.stats["connected_clients"] = len(server_ref.clients)
                    print(f"  - Client disconnected: {self.client_address} "
                          f"(total: {server_ref.stats['connected_clients']})")

        return Handler

    def _render_dashboard_html(self) -> str:
        """A simple HTML page that connects to the WebSocket and shows events."""
        return """<!DOCTYPE html>
<html><head><title>Swarm Dashboard</title>
<style>
  body { font-family: monospace; background: #1a1a1a; color: #e0e0e0; margin: 0; padding: 20px; }
  h1 { color: #7eb3ff; margin: 0 0 10px; }
  .stats { background: #2a2a2a; padding: 10px; border-radius: 4px; margin-bottom: 20px; }
  .stats span { display: inline-block; margin-right: 20px; }
  #events { max-height: 80vh; overflow-y: auto; }
  .event { padding: 6px 10px; margin: 2px 0; border-radius: 3px;
           background: #2a2a2a; border-left: 3px solid #555; }
  .event-subtask_launched { border-left-color: #f0c674; }
  .event-subtask_finished { border-left-color: #b5bd68; }
  .event-retry_added { border-left-color: #cc6666; }
  .event-plan_started, .event-plan_finished { border-left-color: #81a2be; font-weight: bold; }
  .agent { color: #de935f; }
  .role { color: #c1ac72; font-size: 0.9em; }
  .ts { color: #666; font-size: 0.85em; }
</style>
</head>
<body>
<h1>🐝 Swarm Dashboard</h1>
<div class="stats">
  <span><strong>Connected:</strong> <span id="connected">-</span></span>
  <span><strong>Events:</strong> <span id="events_count">0</span></span>
  <span><strong>Status:</strong> <span id="status">connecting...</span></span>
</div>
<div id="events"></div>
<script>
const eventsDiv = document.getElementById('events');
const connectedSpan = document.getElementById('connected');
const statusSpan = document.getElementById('status');
const eventsCountSpan = document.getElementById('events_count');
let eventsCount = 0;

const ws = new WebSocket(`ws://${location.host}/`);
ws.onopen = () => {
  statusSpan.textContent = 'connected';
  statusSpan.style.color = '#b5bd68';
};
ws.onclose = () => {
  statusSpan.textContent = 'disconnected';
  statusSpan.style.color = '#cc6666';
};
ws.onerror = (e) => {
  statusSpan.textContent = 'error';
  statusSpan.style.color = '#cc6666';
};
ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  eventsCount++;
  eventsCountSpan.textContent = eventsCount;
  const div = document.createElement('div');
  div.className = 'event event-' + event.event;
  div.innerHTML = `
    <span class="ts">${new Date(event.ts * 1000).toLocaleTimeString()}</span>
    <span class="agent">${event.agent_id}</span>
    <span class="role">(${event.role})</span>
    <strong>${event.event}</strong>
    <pre style="margin: 4px 0 0; color: #999; font-size: 0.85em;">${JSON.stringify(event.payload, null, 2)}</pre>
  `;
  eventsDiv.prepend(div);
};

// Periodic health check to update "connected" count
setInterval(async () => {
  try {
    const r = await fetch('/health');
    const stats = await r.json();
    connectedSpan.textContent = stats.connected_clients;
  } catch (e) {}
}, 1000);
</script>
</body></html>"""


def main():
    p = argparse.ArgumentParser(description="WebSocket progress server for the swarm")
    p.add_argument("--memory-dir", required=True, help="Swarm run memory dir (contains memory.jsonl)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    memory_dir = Path(args.memory_dir)
    if not memory_dir.exists():
        print(f"❌ Memory dir not found: {memory_dir}", file=sys.stderr)
        sys.exit(1)

    server = SwarmWebSocketServer(memory_dir, args.host, args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()