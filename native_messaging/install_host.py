#!/usr/bin/python3
"""Register the Notesheet Native Messaging host for Chrome or Chromium."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


HOST_NAME = "com.notesheet.capture"
EXTENSION_ID_PATTERN = re.compile(r"[a-p]{32}")


def host_manifest_directory(browser: str) -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if browser == "chrome":
        return config_home / "google-chrome" / "NativeMessagingHosts"
    return config_home / "chromium" / "NativeMessagingHosts"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register Notesheet's Native Messaging host for Chrome or Chromium."
    )
    parser.add_argument("browser", choices=("chrome", "chromium"))
    parser.add_argument("extension_id", help="The ID shown at chrome://extensions")
    args = parser.parse_args()

    if not EXTENSION_ID_PATTERN.fullmatch(args.extension_id):
        parser.error("extension_id must be the 32-character ID shown by Chrome.")

    host_script = Path(__file__).resolve().with_name("notesheet_capture_host.py")
    manifest_directory = host_manifest_directory(args.browser)
    manifest_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_directory / f"{HOST_NAME}.json"
    manifest = {
        "name": HOST_NAME,
        "description": "Capture the screen with Notesheet",
        "path": str(host_script),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{args.extension_id}/"],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Registered Notesheet Native Messaging host: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
