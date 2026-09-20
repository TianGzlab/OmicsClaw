"""A stdio MCP server for the tests, written against the standard library.

Run as ``python fake_server.py [flags]``. It speaks newline-delimited
JSON-RPC 2.0, answers ``initialize`` / ``tools/list`` / ``tools/call``, and
handles each ``tools/call`` on its own thread so a slow tool does not block
the reader — which is what lets a test observe ``notifications/cancelled``
arriving while a call is still running.

Flags:

``--log PATH``            append every message received to PATH, one per line
``--banner``              print a non-JSON line on stdout before anything else
``--crash``               write to stderr and exit 3 before reading anything
``--hang-init``           never answer ``initialize``
``--version V``           answer ``initialize`` with protocol version V
``--page-size N``         split ``tools/list`` into pages of N tools
``--dup-names``           offer two tools whose names sanitise alike
``--ignore-eof``          keep running after stdin closes
``--ignore-sigterm``      ignore SIGTERM
``--spawn-child``         start a grandchild ``sleep`` and log its pid
``--instructions TEXT``   send TEXT as the server's instructions
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the arguments back as JSON.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {"name": "fail", "description": "Always reports an error."},
    {"name": "image", "description": "Returns an image and a caption."},
    {"name": "big", "description": "Returns `size` characters."},
    {"name": "sleep", "description": "Sleeps for `seconds`."},
    {"name": "env", "description": "Reports the environment variable `name`."},
    {"name": "ping-first", "description": "Pings the client before answering."},
    {"name": "structured", "description": "Returns only structured content."},
]

_write_lock = threading.Lock()
_responses: dict[object, dict] = {}
_responses_ready = threading.Condition()


def send(message: dict) -> None:
    with _write_lock:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def log(path: str | None, message: dict) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(message) + "\n")


def text(value: str) -> dict:
    return {"content": [{"type": "text", "text": value}]}


def wait_for_response(request_id: object, timeout: float = 5.0) -> dict | None:
    deadline = time.monotonic() + timeout
    with _responses_ready:
        while request_id not in _responses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            _responses_ready.wait(remaining)
        return _responses.pop(request_id)


def call(request_id: object, name: str, arguments: dict) -> None:
    if name == "echo":
        result = text(json.dumps(arguments, sort_keys=True))
    elif name == "fail":
        result = {"content": [{"type": "text", "text": "it broke"}], "isError": True}
    elif name == "image":
        result = {
            "content": [
                {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
                {"type": "text", "text": "a caption"},
            ]
        }
    elif name == "big":
        result = text("x" * int(arguments.get("size", 0)))
    elif name == "sleep":
        time.sleep(float(arguments.get("seconds", 0)))
        result = text("slept")
    elif name == "env":
        result = text(os.environ.get(arguments.get("name", ""), "<unset>"))
    elif name == "ping-first":
        # Deliberately reuse the id of the call being answered: a client that
        # routes by id alone would take this request for its own response.
        send({"jsonrpc": "2.0", "id": request_id, "method": "ping"})
        pong = wait_for_response(request_id)
        result = text(f"pong: {json.dumps(pong, sort_keys=True)}")
    elif name == "structured":
        result = {"content": [], "structuredContent": {"genes": ["TP53"]}}
    else:
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool {name}"},
            }
        )
        return
    send({"jsonrpc": "2.0", "id": request_id, "result": result})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log")
    parser.add_argument("--banner", action="store_true")
    parser.add_argument("--crash", action="store_true")
    parser.add_argument("--hang-init", action="store_true")
    parser.add_argument("--version", default="2025-06-18")
    parser.add_argument("--page-size", type=int, default=0)
    parser.add_argument("--dup-names", action="store_true")
    parser.add_argument("--ignore-eof", action="store_true")
    parser.add_argument("--ignore-sigterm", action="store_true")
    parser.add_argument("--spawn-child", action="store_true")
    parser.add_argument("--instructions", default="")
    options = parser.parse_args()

    if options.crash:
        sys.stderr.write("fatal: the server could not find its data\n")
        sys.stderr.flush()
        return 3
    if options.ignore_sigterm:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if options.spawn_child:
        child = subprocess.Popen(["sleep", "60"])
        log(options.log, {"grandchild": child.pid})
    if options.banner:
        print("fake MCP server starting up", flush=True)

    tools = list(TOOLS)
    if options.dup_names:
        tools += [{"name": "get-thing"}, {"name": "get_thing"}]

    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        log(options.log, message)
        method = message.get("method")
        request_id = message.get("id")
        if method is None:
            with _responses_ready:
                _responses[request_id] = message
                _responses_ready.notify_all()
            continue
        if request_id is None:
            continue
        if method == "initialize":
            if options.hang_init:
                continue
            result = {
                "protocolVersion": options.version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1.0"},
            }
            if options.instructions:
                result["instructions"] = options.instructions
            send({"jsonrpc": "2.0", "id": request_id, "result": result})
        elif method == "tools/list":
            size = options.page_size or len(tools)
            start = int((message.get("params") or {}).get("cursor") or 0)
            page = {"tools": tools[start : start + size]}
            if start + size < len(tools):
                page["nextCursor"] = str(start + size)
            send({"jsonrpc": "2.0", "id": request_id, "result": page})
        elif method == "tools/call":
            params = message.get("params") or {}
            threading.Thread(
                target=call,
                args=(request_id, params.get("name"), params.get("arguments") or {}),
                daemon=True,
            ).start()
        else:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "method not found"},
                }
            )

    while options.ignore_eof:
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
