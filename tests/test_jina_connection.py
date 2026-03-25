# -*- coding: utf-8 -*-
"""
Jina Reader connectivity check helper.
"""

import json
import sys
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from config.config_loader import load_config


def check_jina_connection(url: str = "https://example.com", timeout: int = 20) -> dict:
    cfg = load_config()
    web_cfg = cfg.get("web_tools_config", {})
    api_key = web_cfg.get("JINA_KEY", "")
    if not api_key:
        return {
            "status": "fail",
            "http_status": None,
            "summary": "JINA_KEY is empty",
            "raw_excerpt": "",
        }

    try:
        response = requests.get(
            f"https://r.jina.ai/{url}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Return-Format": "markdown",
            },
            timeout=timeout,
        )
        raw = response.text
        lowered = raw.lower()
        if response.status_code != 200:
            return {
                "status": "fail",
                "http_status": response.status_code,
                "summary": f"Jina returned HTTP {response.status_code}",
                "raw_excerpt": raw[:500],
            }

        if any(word in lowered for word in ("quota", "unauthorized", "payment required", "invalid", "insufficient")):
            return {
                "status": "fail",
                "http_status": response.status_code,
                "summary": "Jina response indicates auth/quota issue",
                "raw_excerpt": raw[:500],
            }

        if len(raw.strip()) < 100:
            return {
                "status": "fail",
                "http_status": response.status_code,
                "summary": "Jina response body too short",
                "raw_excerpt": raw[:500],
            }

        return {
            "status": "ok",
            "http_status": response.status_code,
            "summary": "Jina returned markdown content",
            "raw_excerpt": raw[:500],
        }
    except Exception as exc:
        return {
            "status": "fail",
            "http_status": None,
            "summary": f"{type(exc).__name__}: {exc}",
            "raw_excerpt": "",
        }


def main() -> int:
    result = check_jina_connection()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
