"""MCP stdio and authenticated local HTTP adapters."""

from __future__ import annotations

import hmac
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TextIO

from .archive import ArchiveError, ValidationError
from .tools import SteadyTools


def error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ArchiveError): return {"success": False, "error": {"code": exc.code, "message": str(exc)}}
    return {"success": False, "error": {"code": "internal_error", "message": "Internal server error"}}


def handle_mcp_request(tools: SteadyTools, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id, method = request.get("id"), request.get("method")
    if request_id is None: return None
    try:
        if method == "initialize": result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "steady-memory", "version": "0.1.0"}}
        elif method == "ping": result = {}
        elif method == "tools/list": result = {"tools": tools.definitions}
        elif method == "tools/call":
            params = request.get("params") or {}; response = tools.call(params.get("name"), params.get("arguments") or {}, str(request_id))
            result = {"content": [{"type": "text", "text": json.dumps(response, ensure_ascii=False)}], "structuredContent": response, "isError": False}
        else: return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        payload = error_payload(exc)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": True}}


def run_mcp(tools: SteadyTools, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> None:
    for line in input_stream or sys.stdin:
        try: response = handle_mcp_request(tools, json.loads(line))
        except json.JSONDecodeError as exc: response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if response is not None:
            (output_stream or sys.stdout).write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"); (output_stream or sys.stdout).flush()


def make_http_handler(tools: SteadyTools, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SteadyMemory/0.1"
        def log_message(self, format: str, *args: Any) -> None: sys.stderr.write("[steady-memory] " + format % args + "\n")
        def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status.value); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def authorized(self) -> bool: return hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")
        def do_GET(self) -> None:
            if self.path == "/health": return self.send_json(HTTPStatus.OK, {"status": "ok"})
            if not self.authorized(): return self.send_json(HTTPStatus.UNAUTHORIZED, {"success": False, "error": {"code": "unauthorized"}})
            if self.path == "/api/tools": return self.send_json(HTTPStatus.OK, {"tools": tools.definitions})
            self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": {"code": "not_found"}})
        def do_POST(self) -> None:
            if self.path != "/api/agent/call": return self.send_json(HTTPStatus.NOT_FOUND, {"success": False, "error": {"code": "not_found"}})
            if not self.authorized(): return self.send_json(HTTPStatus.UNAUTHORIZED, {"success": False, "error": {"code": "unauthorized"}})
            try:
                if self.headers.get_content_type() != "application/json": raise ValidationError("Content-Type must be application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_048_576: raise ValidationError("request body must be 1 byte to 1 MiB")
                body = json.loads(self.rfile.read(length)); self.send_json(HTTPStatus.OK, tools.call(body.get("tool"), body.get("arguments") or {}, self.headers.get("X-Request-Id")))
            except Exception as exc: self.send_json(HTTPStatus.BAD_REQUEST if isinstance(exc, (ArchiveError, json.JSONDecodeError)) else HTTPStatus.INTERNAL_SERVER_ERROR, error_payload(exc))
    return Handler


def run_http(tools: SteadyTools, host: str, port: int, token: str | None) -> None:
    token = token or os.environ.get("STEADY_API_TOKEN")
    if not token: raise ValidationError("HTTP always requires --token or STEADY_API_TOKEN")
    if host not in {"127.0.0.1", "localhost", "::1"}: raise ValidationError("public HTTP binding is disabled; use a secured reverse proxy")
    server = ThreadingHTTPServer((host, port), make_http_handler(tools, token)); print(f"steady-memory listening on http://{host}:{port}", file=sys.stderr)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
