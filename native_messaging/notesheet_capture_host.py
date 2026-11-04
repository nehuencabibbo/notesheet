#!/usr/bin/python3
"""Native Messaging bridge for Notesheet's capture and Chrome shortcut setting."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path


MAX_MESSAGE_SIZE = 1024 * 1024
NOTESHEET_SCRIPT = Path(__file__).resolve().parents[1] / "notesheet.py"


def read_exact(size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        chunk = sys.stdin.buffer.read(size - len(data))
        if not chunk:
            if not data:
                return None
            raise EOFError("Incomplete Native Messaging message.")
        data.extend(chunk)
    return bytes(data)


def read_message() -> dict | None:
    header = read_exact(4)
    if header is None:
        return None
    (message_size,) = struct.unpack("=I", header)
    if message_size > MAX_MESSAGE_SIZE:
        raise ValueError("Native Messaging request is too large.")
    payload = read_exact(message_size)
    if payload is None:
        raise EOFError("Native Messaging request has no payload.")
    message = json.loads(payload)
    if not isinstance(message, dict):
        raise ValueError("Native Messaging request must be a JSON object.")
    return message


def write_message(message: dict) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(payload)))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        request = read_message()
        if request is None:
            return 0
        action = request.get("action")
        if action == "get-shortcut":
            if not NOTESHEET_SCRIPT.is_file():
                raise FileNotFoundError(f"Notesheet was not found at {NOTESHEET_SCRIPT}.")
            result = subprocess.run(
                [sys.executable, str(NOTESHEET_SCRIPT), "get-chrome-shortcut"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "Could not read shortcut setting.")
            write_message({"ok": True, "binding": result.stdout.strip()})
            return 0
        if action != "capture":
            write_message({"ok": False, "error": "Unsupported action."})
            return 0
        if not NOTESHEET_SCRIPT.is_file():
            raise FileNotFoundError(f"Notesheet was not found at {NOTESHEET_SCRIPT}.")

        result = subprocess.run(
            [sys.executable, str(NOTESHEET_SCRIPT), "capture"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            check=False,
        )
        write_message({"ok": result.returncode == 0})
        return 0
    except Exception as exc:
        write_message({"ok": False, "error": str(exc)})
        return 0


if __name__ == "__main__":
    sys.exit(main())
