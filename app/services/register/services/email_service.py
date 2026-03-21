"""Email service for temporary inbox creation."""
from __future__ import annotations

import os
import random
import string
from typing import Tuple, Optional

import requests

from app.core.config import get_config


class EmailService:
    """Email service wrapper."""

    def __init__(
        self,
        worker_domain: Optional[str] = None,
        email_domain: Optional[str] = None,
        admin_password: Optional[str] = None,
        site_password: Optional[str] = None,
        proxy_url: Optional[str] = None,
    ) -> None:
        self.worker_domain = (
            (worker_domain or get_config("register.worker_domain", "") or os.getenv("WORKER_DOMAIN", "")).strip()
        )
        self.email_domain = (
            (email_domain or get_config("register.email_domain", "") or os.getenv("EMAIL_DOMAIN", "")).strip()
        )
        self.admin_password = (
            (admin_password or get_config("register.admin_password", "") or os.getenv("ADMIN_PASSWORD", "")).strip()
        )
        self.site_password = (
            (site_password or get_config("register.site_password", "") or os.getenv("SITE_PASSWORD", "")).strip()
        )
        self.proxy_url = (
            (
                proxy_url
                or get_config("register.proxy_url", "")
                or os.getenv("REGISTER_PROXY_URL", "")
                or get_config("grok.base_proxy_url", "")
                or os.getenv("BASE_PROXY_URL", "")
            ).strip()
        )

        if not all([self.worker_domain, self.email_domain, self.admin_password]):
            raise ValueError(
                "Missing required email settings: register.worker_domain, register.email_domain, "
                "register.admin_password"
            )

    def _private_site_headers(self) -> dict:
        """Optional headers for private-site protected email services."""
        # Many Cloudflare temp-mail workers protect all endpoints via an
        # additional password gate checked through `x-custom-auth`.
        # Keep backward compatibility:
        # - prefer explicit `site_password`
        # - fallback to `admin_password`
        auth = (self.site_password or self.admin_password or "").strip()
        if not auth:
            return {}
        return {
            "x-custom-auth": auth,
            # Compatibility for variants that use a dedicated site-password header.
            "x-site-password": auth,
        }

    def _generate_random_name(self) -> str:
        letters1 = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 6)))
        numbers = "".join(random.choices(string.digits, k=random.randint(1, 3)))
        letters2 = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 5)))
        return letters1 + numbers + letters2

    def _proxies(self) -> Optional[dict]:
        if not self.proxy_url:
            return None
        return {"http": self.proxy_url, "https": self.proxy_url}

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """Create a temporary mailbox. Returns (jwt, address)."""
        url = f"https://{self.worker_domain}/admin/new_address"
        try:
            random_name = self._generate_random_name()
            res = requests.post(
                url,
                json={
                    "enablePrefix": True,
                    "name": random_name,
                    "domain": self.email_domain,
                },
                headers={
                    "x-admin-auth": self.admin_password,
                    "Content-Type": "application/json",
                    **self._private_site_headers(),
                },
                proxies=self._proxies(),
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                return data.get("jwt"), data.get("address")
            print(f"[-] Email create failed: {res.status_code} - {res.text}")
        except Exception as exc:  # pragma: no cover - network/remote errors
            print(f"[-] Email create error ({url}): {exc}")
        return None, None

    def fetch_first_email(self, jwt: str) -> Optional[str]:
        """Fetch the first email content for the mailbox."""
        try:
            res = requests.get(
                f"https://{self.worker_domain}/api/mails",
                params={"limit": 10, "offset": 0},
                headers={
                    "Authorization": f"Bearer {jwt}",
                    "Content-Type": "application/json",
                    **self._private_site_headers(),
                },
                proxies=self._proxies(),
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("results"):
                    return data["results"][0].get("raw")
            return None
        except Exception as exc:  # pragma: no cover - network/remote errors
            print(f"Email fetch failed: {exc}")
            return None
