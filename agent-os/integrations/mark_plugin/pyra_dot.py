"""
Mark-LIII plugin: route user requests through Dot → PYRA Master.

Drop this file into Mark-LIII/plugins/ (copy or sync). No main.py changes.
Uses stdlib only so a broken Mark venv still loads the plugin.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PLUGIN = {
    "name": "pyra_dot",
    "description": (
        "Send a request to PYRA through Dot (the command router). "
        "Use when the user says Dot should ask PYRA to do something, "
        "or asks PYRA to create/switch projects, report status, list capabilities, "
        "or bring up / discover a connected development board. "
        "Do NOT use for ordinary Mark-local actions like volume or opening apps."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {
                "type": "STRING",
                "description": "The user's request in their words, forwarded to PYRA",
            },
            "project_id": {
                "type": "STRING",
                "description": "Optional project id if the user named one",
            },
        },
        "required": ["text"],
    },
    "tier": "core",
}


def _endpoint() -> str:
    base = os.environ.get("PYRA_DOT_URL", "http://127.0.0.1:8765").rstrip("/")
    return f"{base}/dot/v1/interact"


def _token() -> str:
    return os.environ.get("PYRA_TOKEN", "dev-local-token")


def run(parameters: dict, player=None, session_memory=None) -> str:
    text = str((parameters or {}).get("text") or "").strip()
    if not text:
        return "No request text was given for PYRA."

    project_id = (parameters or {}).get("project_id") or None
    payload = {
        "text": text,
        "source": "mark",
        "project_id": project_id,
        "mark_confirm_available": True,
        "metadata": {"from_mark": True},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_token()}",
    }
    req = urllib.request.Request(_endpoint(), data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return f"Dot could not reach PYRA (HTTP {exc.code}): {detail}"
    except Exception as exc:
        return (
            f"Dot could not reach PYRA Master at {_endpoint()}. "
            f"Is the service running? ({type(exc).__name__}: {exc})"
        )

    speech = str(body.get("speech") or "").strip()
    hud = body.get("hud")
    if player and hud and isinstance(hud, dict):
        try:
            title = hud.get("title") or "PYRA"
            content = hud.get("body") or speech
            player.show_content(title, content)
        except Exception:
            pass
    if player:
        try:
            player.write_log(f"Dot→PYRA: {body.get('capability') or body.get('status')}")
        except Exception:
            pass

    return speech or "PYRA returned an empty reply."
