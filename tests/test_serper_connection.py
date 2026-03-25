# -*- coding: utf-8 -*-
"""
Serper connectivity check helper.
"""

import json
import sys
from pathlib import Path

import http.client

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from config.config_loader import load_config


def check_serper_connection(query: str = "OpenAI", timeout: int = 15) -> dict:
    cfg = load_config()
    web_cfg = cfg.get("web_tools_config", {})
    api_key = web_cfg.get("SERPER_KEY", "")
    if not api_key:
        return {
            "status": "fail",
            "http_status": None,
            "summary": "SERPER_KEY is empty",
            "raw_excerpt": "",
        }

    conn = http.client.HTTPSConnection("google.serper.dev", timeout=timeout)
    try:
        payload = json.dumps({"q": query, "num": 1, "hl": "en", "gl": "us"})
        conn.request(
            "POST",
            "/search",
            payload,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        lowered = raw.lower()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "status": "fail",
                "http_status": response.status,
                "summary": "Serper returned non-JSON response",
                "raw_excerpt": raw[:500],
            }

        if response.status != 200:
            return {
                "status": "fail",
                "http_status": response.status,
                "summary": f"Serper returned HTTP {response.status}",
                "raw_excerpt": raw[:500],
            }

        if any(word in lowered for word in ("quota", "unauthorized", "invalid", "payment", "exceeded")):
            return {
                "status": "fail",
                "http_status": response.status,
                "summary": "Serper response indicates auth/quota issue",
                "raw_excerpt": raw[:500],
            }

        organic = data.get("organic", [])
        if not isinstance(organic, list):
            return {
                "status": "fail",
                "http_status": response.status,
                "summary": "Serper response missing organic results list",
                "raw_excerpt": raw[:500],
            }

        return {
            "status": "ok",
            "http_status": response.status,
            "summary": f"Serper returned {len(organic)} organic results",
            "raw_excerpt": raw[:500],
        }
    except Exception as exc:
        return {
            "status": "fail",
            "http_status": None,
            "summary": f"{type(exc).__name__}: {exc}",
            "raw_excerpt": "",
        }
    finally:
        conn.close()


def main() -> int:
    result = check_serper_connection()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
