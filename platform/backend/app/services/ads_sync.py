"""Reklam harcaması senkronu (gece job'u). Meta Marketing API Insights, kampanya × gün."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import httpx

from ..core.config import get_settings
from ..core.db import db
from ..domain.money import money


async def sync_meta_spend(since: date, until: date) -> int:
    s = get_settings()
    if not (s.meta_access_token and s.meta_ad_account_id):
        return 0
    url = f"https://graph.facebook.com/v21.0/act_{s.meta_ad_account_id}/insights"
    params: dict | None = {
        "access_token": s.meta_access_token,
        "level": "campaign",
        "time_increment": 1,
        "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions",
        "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
        "limit": 500,
    }
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as c:
        while url:
            r = await c.get(url, params=params)
            r.raise_for_status()
            body = r.json()
            rows.extend(body.get("data", []))
            url = body.get("paging", {}).get("next")
            params = None  # "next" URL tüm parametreleri içerir

    n = 0
    for row in rows:
        camp = await db.adcampaign.upsert(
            where={"platform_externalId": {"platform": "META", "externalId": row["campaign_id"]}},
            data={
                "create": {"platform": "META", "externalId": row["campaign_id"], "name": row["campaign_name"]},
                "update": {"name": row["campaign_name"]},
            },
        )
        day = datetime.fromisoformat(row["date_start"]).replace(tzinfo=UTC)
        leads = sum(int(a["value"]) for a in row.get("actions", []) if a.get("action_type") == "lead")
        values = {
            "spend": money(row.get("spend", "0")),
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "platformLeads": leads,
        }
        await db.adspenddaily.upsert(
            where={"campaignId_date": {"campaignId": camp.id, "date": day}},
            data={"create": {"campaignId": camp.id, "date": day, **values}, "update": values},
        )
        n += 1
    return n


async def sync_recent(days: int = 3) -> int:
    """Meta harcamaları geriye dönük düzeltebilir; son 3 gün her gece yeniden çekilir."""
    today = date.today()
    return await sync_meta_spend(today - timedelta(days=days), today - timedelta(days=1))
