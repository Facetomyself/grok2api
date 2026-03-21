from __future__ import annotations

import datetime
import random
from typing import Any, Dict, Optional

from curl_cffi import requests
from app.core.config import get_config

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def generate_random_birthdate() -> str:
    """Generate a random birth date between 20 and 40 years old."""
    today = datetime.date.today()
    age = random.randint(20, 40)
    birth_year = today.year - age
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    return f"{birth_year}-{birth_month:02d}-{birth_day:02d}T16:00:00.000Z"


class BirthDateService:
    """Set account birth date via Grok REST API."""

    def __init__(self, cf_clearance: str = "", proxy_url: str = ""):
        self.cf_clearance = (cf_clearance or "").strip()
        self.proxy_url = (
            str(proxy_url or "").strip()
            or str(get_config("register.proxy_url", "") or "").strip()
            or str(get_config("grok.base_proxy_url", "") or "").strip()
        )

    def set_birth_date(
        self,
        sso: str,
        sso_rw: str,
        impersonate: str,
        user_agent: Optional[str] = None,
        cf_clearance: Optional[str] = None,
        session: Any = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        if not sso:
            return {
                "ok": False,
                "status_code": None,
                "response_text": "",
                "error": "missing sso",
            }
        if not sso_rw:
            return {
                "ok": False,
                "status_code": None,
                "response_text": "",
                "error": "missing sso-rw",
            }

        url = "https://grok.com/rest/auth/set-birth-date"
        cookies = {
            "sso": sso,
            "sso-rw": sso_rw,
        }
        clearance = (cf_clearance if cf_clearance is not None else self.cf_clearance).strip()
        if clearance:
            cookies["cf_clearance"] = clearance

        headers = {
            "content-type": "application/json",
            "origin": "https://grok.com",
            "referer": "https://grok.com/",
            "user-agent": user_agent or DEFAULT_USER_AGENT,
        }
        payload = {"birthDate": generate_random_birthdate()}

        def _post_once(req_cookies: Dict[str, str]):
            if session is not None:
                return session.post(
                    url,
                    headers=headers,
                    cookies=req_cookies,
                    json=payload,
                    timeout=timeout,
                )
            return requests.post(
                url,
                headers=headers,
                cookies=req_cookies,
                json=payload,
                impersonate=impersonate or "chrome120",
                proxy=self.proxy_url or None,
                timeout=timeout,
            )

        retried = False
        try:
            response = _post_once(cookies)
            # Best-effort retry when Cloudflare challenge blocks the first attempt.
            if response.status_code == 403 and session is not None:
                retried = True
                try:
                    session.get(
                        "https://grok.com/",
                        headers={"user-agent": headers["user-agent"]},
                        timeout=min(timeout, 10),
                    )
                except Exception:
                    pass

                refreshed_clearance = str(session.cookies.get("cf_clearance") or "").strip()
                retry_cookies = dict(cookies)
                if refreshed_clearance:
                    retry_cookies["cf_clearance"] = refreshed_clearance
                response = _post_once(retry_cookies)

            status_code = response.status_code
            response_text = response.text or ""
            ok = status_code == 200
            return {
                "ok": ok,
                "status_code": status_code,
                "response_text": response_text,
                "error": None if ok else f"HTTP {status_code}",
                "retried": retried,
            }
        except Exception as e:
            return {
                "ok": False,
                "status_code": None,
                "response_text": "",
                "error": str(e),
                "retried": retried,
            }
