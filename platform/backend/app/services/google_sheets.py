"""Google Sheets API istemcisi (servis hesabı, ek kütüphane gerektirmez).

Kimlik: servis hesabı JSON anahtarıyla RS256 imzalı JWT → OAuth erişim token'ı.
Okuma `spreadsheets.readonly` kapsamıyla yapılır; BİLANÇO'ya yazma ayrıca açılmadıkça istenmez.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx
import jwt

from ..core.config import get_settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://sheets.googleapis.com/v4/spreadsheets"
READ_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class SheetsError(Exception):
    pass


class SheetsReader(Protocol):
    async def sheet_titles(self, spreadsheet_id: str) -> list[str]: ...

    async def read_sheets(self, spreadsheet_id: str, titles: list[str]) -> dict[str, list[list[object]]]: ...


def _service_account() -> dict:
    raw = get_settings().google_service_account_json.strip()
    if not raw:
        raise SheetsError("GOOGLE_SERVICE_ACCOUNT_JSON tanımlı değil")
    try:
        return json.loads(raw if raw.startswith("{") else Path(raw).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SheetsError(f"Servis hesabı anahtarı okunamadı: {e}") from e


class GoogleSheetsClient:
    def __init__(self, write: bool = False) -> None:
        self.sa = _service_account()
        self.scope = WRITE_SCOPE if write else READ_SCOPE
        self._token: tuple[str, float] | None = None

    @property
    def email(self) -> str:
        return self.sa.get("client_email", "")

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": self.sa["client_email"], "scope": self.scope, "aud": TOKEN_URL, "iat": now, "exp": now + 3600},
            self.sa["private_key"],
            algorithm="RS256",
        )
        r = await client.post(
            TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        )
        if r.status_code != 200:
            raise SheetsError(f"Google kimlik doğrulama hatası: {r.text[:200]}")
        body = r.json()
        self._token = (body["access_token"], now + int(body.get("expires_in", 3600)))
        return self._token[0]

    async def _get(self, url: str, params: dict | list) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {await self._access_token(c)}"})
        if r.status_code == 403:
            raise SheetsError(f"Erişim yok: tabloyu {self.email} ile paylaşın")
        if r.status_code == 404:
            raise SheetsError("Tablo bulunamadı (DRIVE_INCOME_SPREADSHEET_ID'yi kontrol edin)")
        r.raise_for_status()
        return r.json()

    async def sheet_titles(self, spreadsheet_id: str) -> list[str]:
        body = await self._get(f"{API}/{spreadsheet_id}", {"fields": "sheets.properties(title,hidden)"})
        return [s["properties"]["title"] for s in body.get("sheets", []) if not s["properties"].get("hidden")]

    async def read_sheets(self, spreadsheet_id: str, titles: list[str]) -> dict[str, list[list[object]]]:
        """Tüm sayfalar tek istekte. UNFORMATTED_VALUE: tutarlar sayı olarak gelir, biçim farkı sorun olmaz."""
        params: list[tuple[str, str]] = [("valueRenderOption", "UNFORMATTED_VALUE"), ("majorDimension", "ROWS")]
        params += [("ranges", f"'{t.replace(chr(39), chr(39) * 2)}'") for t in titles]
        body = await self._get(f"{API}/{spreadsheet_id}/values:batchGet", params)
        out: dict[str, list[list[object]]] = {}
        for title, vr in zip(titles, body.get("valueRanges", []), strict=False):
            out[title] = vr.get("values", [])
        return out

    async def write_range(self, spreadsheet_id: str, a1: str, values: list[list[object]]) -> None:
        if self.scope != WRITE_SCOPE:
            raise SheetsError("Yazma kapsamı açık değil")
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.put(
                f"{API}/{spreadsheet_id}/values/{quote(a1)}",
                params={"valueInputOption": "USER_ENTERED"},
                json={"range": a1, "majorDimension": "ROWS", "values": values},
                headers={"Authorization": f"Bearer {await self._access_token(c)}"},
            )
        if r.status_code == 403:
            raise SheetsError(f"Yazma yetkisi yok: tabloyu {self.email} ile Düzenleyen olarak paylaşın")
        r.raise_for_status()
