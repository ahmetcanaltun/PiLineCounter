"""
Optional config sync daemon - polls a remote backend every 10 seconds.

- When configVersion changes: line/mode/roi are re-applied and config.json is updated.
- When snapshotRequested is true: a JPEG frame is captured and uploaded.

The device only makes outbound HTTPS calls, so no inbound access is required.
Disabled automatically unless API_BASE_URL and DEVICE_TOKEN are set.
"""

import json
import os
import threading
import time
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

CONFIG_PATH = Path(__file__).parent / "config.json"
POLL_INTERVAL_DEFAULT = 10  # seconds


class ConfigSync(threading.Thread):
    def __init__(self, processor, interval=POLL_INTERVAL_DEFAULT):
        super().__init__(daemon=True, name="ConfigSync")
        self.processor = processor
        self.interval = interval
        self.api_url = (os.getenv("API_BASE_URL") or "").rstrip("/")
        self.device_id = os.getenv("DEVICE_ID", "device-01")
        self.token = os.getenv("DEVICE_TOKEN")
        self.last_version = -1
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        if not REQUESTS_AVAILABLE:
            print("[CONFIG_SYNC] requests not installed - sync disabled.")
            return
        if not (self.api_url and self.token):
            print("[CONFIG_SYNC] API_BASE_URL or DEVICE_TOKEN not set - sync disabled.")
            return

        print(f"[CONFIG_SYNC] started - {self.api_url} device={self.device_id} interval={self.interval}s")
        while not self._stop_event.is_set():
            try:
                self._sync_once()
            except Exception as exc:
                print(f"[CONFIG_SYNC] loop error: {exc}")
            self._stop_event.wait(self.interval)

    def _sync_once(self):
        url = f"{self.api_url}/api/devices/{self.device_id}/config"
        headers = {"X-Device-Token": self.token}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            print(f"[CONFIG_SYNC] config GET {r.status_code}: {r.text[:200]}")
            return
        cfg = r.json()
        new_version = cfg.get("configVersion", 0)

        if new_version != self.last_version:
            self._apply_config(cfg)
            self.last_version = new_version

        if cfg.get("snapshotRequested"):
            self._upload_snapshot(headers)

    def _apply_config(self, cfg):
        line = cfg.get("line")
        mode = cfg.get("mode")
        flip = cfg.get("flipDirection", False)

        self.processor.update_config(line=line, mode=mode, flip_direction=flip)
        roi = cfg.get("roi")
        if roi:
            self.processor.update_roi(roi)

        # Persist locally so the device keeps its settings across reboots
        try:
            payload = {
                "line": line,
                "mode": mode,
                "flip_direction": flip,
                "roi": roi,
                "config_version": cfg.get("configVersion"),
            }
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[CONFIG_SYNC] could not write config.json: {exc}")

        print(f"[CONFIG_SYNC] applied config v{cfg.get('configVersion')}: line={line} mode={mode} flip={flip}")

    def _upload_snapshot(self, headers):
        frame = self.processor.get_frame()
        if not frame:
            print("[CONFIG_SYNC] no frame available, skipping snapshot")
            return
        url = f"{self.api_url}/api/devices/{self.device_id}/snapshot"
        try:
            r = requests.post(
                url,
                headers=headers,
                files={"snapshot": ("snap.jpg", frame, "image/jpeg")},
                timeout=15,
            )
            if r.status_code >= 400:
                print(f"[CONFIG_SYNC] snapshot upload {r.status_code}: {r.text[:200]}")
            else:
                print(f"[CONFIG_SYNC] snapshot upload OK ({len(frame)} byte)")
        except Exception as exc:
            print(f"[CONFIG_SYNC] snapshot upload error: {exc}")
