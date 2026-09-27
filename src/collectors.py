"""Collecte des données brutes. Chaque fonction échoue « proprement » : en cas de panne
d'une source, elle renvoie une valeur vide et le reste du système continue."""
from __future__ import annotations

import hashlib
import os
import time
from calendar import timegm
from typing import Any

import feedparser

from .common import http_get, log
from .reliability import tier_for_url

COINGECKO = "https://api.coingecko.com/api/v3"
LLAMA = "https://api.llama.fi"
STABLES = "https://stablecoins.llama.fi"
X_API = "https://api.x.com/2"


# ── Prix (CoinGecko, gratuit avec une clé « Demo ») ───────────────────────────
def coingecko_top100() -> list[dict[str, Any]]:
    headers = {}
    key = os.getenv("COINGECKO_API_KEY")
    if key:
        headers["x-cg-demo-api-key"] = key
    r = http_get(
        f"{COINGECKO}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "price_change_percentage": "1h,24h,7d",
        },
        headers=headers,
    )
    return r.json() if r else []


def priority_market(cfg: dict, top: list[dict]) -> list[dict]:
    by_id = {c.get("id"): c for c in top}
    out = []
    for a in cfg["priority_assets"]:
        c = by_id.get(a["coingecko_id"])
        out.append(
            {
                "symbol": a["symbol"],
                "name": a.get("name", a["symbol"]),
                "price": c.get("current_price") if c else None,
                "change1h": c.get("price_change_percentage_1h_in_currency") if c else None,
                "change24h": c.get("price_change_percentage_24h_in_currency") if c else None,
                "change7d": c.get("price_change_percentage_7d_in_currency") if c else None,
                "volume": c.get("total_volume") if c else None,
                "marketCapRank": c.get("market_cap_rank") if c else None,
                "lastUpdated": c.get("last_updated") if c else None,
            }
        )
    return out


def fear_greed() -> dict | None:
    r = http_get("https://api.alternative.me/fng/", params={"limit": 2})
    if not r:
        return None
    d = r.json().get("data") or []
    if not d:
        return None
    return {"value": int(d[0]["value"]), "label": d[0]["value_classification"], "yesterday": int(d[1]["value"]) if len(d) > 1 else None}


# ── On-chain (DefiLlama, gratuit) ─────────────────────────────────────────────
def onchain_snapshot(cfg: dict) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    r = http_get(f"{LLAMA}/v2/chains")
    if r:
        chains = {c.get("name"): c.get("tvl") for c in r.json()}
        snap["chainTVL"] = {a["symbol"]: chains.get(a["defillama_chain"]) for a in cfg["priority_assets"] if a.get("defillama_chain")}
    for a in cfg["priority_assets"]:
        slug = a.get("defillama_protocol")
        if not slug:
            continue
        r = http_get(f"{LLAMA}/tvl/{slug}")
        if r:
            try:
                snap.setdefault("protocolTVL", {})[a["symbol"]] = float(r.text)
            except ValueError:
                pass
        r = http_get(f"{LLAMA}/summary/fees/{slug}", params={"dataType": "dailyFees"})
        if r:
            snap.setdefault("fees24h", {})[a["symbol"]] = r.json().get("total24h")
    r = http_get(f"{STABLES}/stablecoins", params={"includePrices": "true"})
    if r:
        total = 0.0
        for s in r.json().get("peggedAssets", []):
            total += float((s.get("circulating") or {}).get("peggedUSD") or 0)
        snap["stablecoinsTotal"] = total
    r = http_get(f"{LLAMA}/overview/dexs", params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"})
    if r:
        snap["dexVolume24h"] = r.json().get("total24h")
    return snap


# ── Actualités (RSS) ──────────────────────────────────────────────────────────
def _item_id(url: str, title: str) -> str:
    return hashlib.sha1((url or title).encode("utf-8")).hexdigest()[:16]


def rss_items(cfg: dict, since_hours: float) -> list[dict[str, Any]]:
    cutoff = time.time() - since_hours * 3600
    items: list[dict[str, Any]] = []
    for feed in cfg.get("rss_feeds", []):
        try:
            parsed = feedparser.parse(feed["url"], agent="crypto-intel/1.0")
        except Exception as e:  # noqa: BLE001 — un flux cassé ne doit rien bloquer
            log.warning("Flux RSS en échec (%s) : %s", feed["name"], e)
            continue
        if parsed.bozo and not parsed.entries:
            log.warning("Flux RSS illisible : %s", feed["name"])
            continue
        for e in parsed.entries[:40]:
            ts_struct = e.get("published_parsed") or e.get("updated_parsed")
            ts = timegm(ts_struct) if ts_struct else time.time()
            if ts < cutoff:
                continue
            url = e.get("link", "")
            title = (e.get("title") or "").strip()
            items.append(
                {
                    "id": "rss:" + _item_id(url, title),
                    "kind": "news",
                    "title": title,
                    "summary": (e.get("summary") or "")[:500],
                    "url": url,
                    "source": feed["name"],
                    "tier": min(feed.get("tier", 3), tier_for_url(cfg, url)),
                    "ts": ts,
                }
            )
    return items


# ── X / Twitter (optionnel, payant à l'usage) ─────────────────────────────────
def x_posts(cfg: dict, state: dict) -> list[dict[str, Any]]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    out: list[dict[str, Any]] = []
    for acc in cfg.get("x_accounts", []):
        uid = acc.get("id")
        if not uid:
            continue  # tant que l'id numérique n'est pas renseigné, on ne surveille pas ce compte
        params = {"max_results": 5, "tweet.fields": "created_at", "exclude": "retweets,replies"}
        since = state["x_since"].get(str(uid))
        if since:
            params["since_id"] = since
        r = http_get(f"{X_API}/users/{uid}/tweets", params=params, headers=headers)
        if not r:
            continue
        data = r.json().get("data") or []
        if data:
            state["x_since"][str(uid)] = data[0]["id"]
        for t in data:
            out.append(
                {
                    "id": "x:" + t["id"],
                    "kind": "x",
                    "title": t.get("text", "")[:280],
                    "summary": "",
                    "url": f"https://x.com/{acc['handle']}/status/{t['id']}",
                    "source": "@" + acc["handle"],
                    "xUserId": str(uid),
                    "xRole": acc.get("role"),
                    "asset": acc.get("asset"),
                    # Compte officiel vérifié par son id → équivalent tier 1 pour ses propres annonces
                    "tier": 1 if acc.get("role") == "official" else 3,
                    "ts": time.time(),
                }
            )
    return out


def price_anomalies(cfg: dict, top: list[dict]) -> list[dict[str, Any]]:
    """Détecte les mouvements anormaux. Données chiffrées → pas besoin d'IA pour les classer."""
    a = cfg["alerts"]
    prio_ids = {x["coingecko_id"]: x["symbol"] for x in cfg["priority_assets"]}
    out = []
    hour_bucket = int(time.time() // 3600)
    for c in top:
        sym = (c.get("symbol") or "").upper()
        ch1 = c.get("price_change_percentage_1h_in_currency")
        ch24 = c.get("price_change_percentage_24h_in_currency")
        if c.get("id") in prio_ids and ch1 is not None and abs(ch1) >= a["priority_move_1h_important"]:
            level = "critical" if abs(ch1) >= a["priority_move_1h_critical"] else "important"
            out.append({
                "id": f"move:{c['id']}:{hour_bucket}", "kind": "price", "level": level,
                "title": f"{prio_ids[c['id']]} {'+' if ch1 > 0 else ''}{ch1:.1f} % en 1 h",
                "summary": f"Prix : {c.get('current_price')} $ ; 24 h : {ch24:.1f} %." if ch24 is not None else "",
                "url": f"https://www.coingecko.com/en/coins/{c['id']}", "source": "CoinGecko", "tier": 1,
                "assets": [prio_ids[c["id"]]], "ts": time.time(),
            })
        elif c.get("id") not in prio_ids and ch24 is not None and abs(ch24) >= a["top100_move_24h_important"]:
            day_bucket = int(time.time() // 86400)
            out.append({
                "id": f"move24:{c['id']}:{day_bucket}", "kind": "price", "level": "important",
                "title": f"{sym} {'+' if ch24 > 0 else ''}{ch24:.1f} % en 24 h (rang {c.get('market_cap_rank')})",
                "summary": "Mouvement inhabituel dans le top 100 : cause à vérifier.",
                "url": f"https://www.coingecko.com/en/coins/{c['id']}", "source": "CoinGecko", "tier": 1,
                "assets": [sym], "ts": time.time(),
            })
    return out
