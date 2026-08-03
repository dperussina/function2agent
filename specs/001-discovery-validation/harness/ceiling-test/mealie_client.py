"""SPIKE - E7 ceiling test. Delete after 2026-11-30. Do not import from product code.

Thin HTTP client for the disposable Mealie instance. Used by the seeder, the oracle,
and arm A's hand-written tools. Every call goes over the application's external HTTP
interface; nothing touches the database directly except the snapshot/restore path,
which is fixture management rather than agent capability.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class MealieError(RuntimeError):
    def __init__(self, status: int, body: str, method: str, path: str):
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


class MealieClient:
    def __init__(self, base_url: str, email: str, password: str, timeout: int = 45):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token = self._login(email, password)

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, *, body=None, form=None, token=None):
        url = self.base_url + path
        headers = {"Accept": "application/json"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        tok = token if token is not None else getattr(self, "_token", None)
        if tok:
            headers["Authorization"] = "Bearer " + tok
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as exc:
            raise MealieError(exc.code, exc.read().decode(), method, path) from None

    def _login(self, email: str, password: str) -> str:
        out = self._request(
            "POST", "/api/auth/token", form={"username": email, "password": password}, token=""
        )
        return out["access_token"]

    @property
    def token(self) -> str:
        return self._token

    def get(self, path: str, **params):
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                path = path + ("&" if "?" in path else "?") + urllib.parse.urlencode(clean, doseq=True)
        return self._request("GET", path)

    def post(self, path: str, body=None):
        return self._request("POST", path, body=body)

    def put(self, path: str, body=None):
        return self._request("PUT", path, body=body)

    def patch(self, path: str, body=None):
        return self._request("PATCH", path, body=body)

    def delete(self, path: str):
        return self._request("DELETE", path)

    # -- paging helper -----------------------------------------------------

    def get_all(self, path: str, per_page: int = 100, **params) -> list:
        items: list = []
        page = 1
        while True:
            out = self.get(path, page=page, perPage=per_page, **params)
            batch = out.get("items", []) if isinstance(out, dict) else out
            items.extend(batch)
            if not isinstance(out, dict):
                break
            if page >= (out.get("total_pages") or 1):
                break
            page += 1
        return items


def connect() -> MealieClient:
    cfg = load_config()["target"]
    return MealieClient(cfg["base_url"], cfg["admin_email"], cfg["admin_password"])
