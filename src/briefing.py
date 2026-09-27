"""Briefing quotidien de 06:30.

Usage :  python -m src.briefing            (respecte le créneau horaire)
         python -m src.briefing --force    (génère tout de suite)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import anthropic

from . import collectors, notify
from .common import BRIEF_DIR, DATA_DIR, extract_json, load_config, load_state, log, now_local, now_utc_iso, read_json, read_prompt, save_state, write_json

LISTS = ["tldr", "news", "market", "x", "projects", "smartMoney", "unlocks", "regulation", "macro", "onchain", "watchlist", "breaking"]
IMPACTS = {"pos", "neu", "neg"}
CONFS = {"confirmed", "likely", "unconfirmed", "rumor"}


def in_window(cfg: dict) -> bool:
    """Deux déclenchements UTC couvrent l'heure d'été et d'hiver ; on ne garde que celui
    qui tombe entre 06:00 et 08:59 à Paris, et une seule fois par jour."""
    now = now_local(cfg)
    if not (6 <= now.hour <= 8):
        log.info("Hors créneau (%s à Paris) : rien à faire.", now.strftime("%H:%M"))
        return False
    if (BRIEF_DIR / f"{now.date().isoformat()}.json").exists():
        log.info("Le briefing du jour existe déjà.")
        return False
    return True


def gather_context(cfg: dict, state: dict) -> tuple[dict, list[dict]]:
    top = collectors.coingecko_top100()
    prio = collectors.priority_market(cfg, top)
    ctx = {
        "prioritaires": prio,
        "top100_mouvements_24h": sorted(
            [
                {"symbol": (c.get("symbol") or "").upper(), "rang": c.get("market_cap_rank"), "var24h": c.get("price_change_percentage_24h_in_currency"), "var7j": c.get("price_change_percentage_7d_in_currency")}
                for c in top
                if c.get("price_change_percentage_24h_in_currency") is not None
            ],
            key=lambda x: abs(x["var24h"] or 0),
            reverse=True,
        )[:15],
        "fear_greed": collectors.fear_greed(),
        "onchain": collectors.onchain_snapshot(cfg),
        "actualites_24h": [
            {"titre": i["title"], "source": i["source"], "tier": i["tier"], "url": i["url"], "heure_utc": datetime.fromtimestamp(i["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M")}
            for i in collectors.rss_items(cfg, since_hours=26)
        ][:120],
        "x_recents": [r for r in state.get("recent", []) if r.get("kind") == "x"][-60:],
        "alertes_depuis_hier": state.get("digest_queue", [])[-20:],
    }
    return ctx, prio


def call_claude(cfg: dict, ctx: dict, today: str) -> dict:
    client = anthropic.Anthropic()
    system = read_prompt("briefing_system.md")
    user = (
        f"Nous sommes le {today}. Rédige le Crypto Daily de 06:30.\n"
        "Utilise la recherche web pour vérifier, compléter et sourcer (unlocks à venir, régulation, X, nouveaux projets, macro).\n\n"
        "<donnees_non_fiables>\n" + json.dumps(ctx, ensure_ascii=False, default=str) + "\n</donnees_non_fiables>"
    )
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": int(cfg["models"].get("max_web_searches", 15))}]
    text_parts: list[str] = []
    for _ in range(6):  # les recherches longues peuvent demander plusieurs tours (« pause_turn »)
        resp = client.messages.create(model=cfg["models"]["briefing"], max_tokens=16000, system=system, messages=messages, tools=tools)
        text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        if resp.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": user}, {"role": "assistant", "content": resp.content}]
    return extract_json("".join(text_parts))


def _safe_url(u: str | None) -> str | None:
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) else None


def sanitize(b: dict, today: str) -> dict:
    """Garde-fous : structure attendue, valeurs autorisées, liens http(s) uniquement."""
    b = {k: v for k, v in b.items() if k in LISTS + ["date", "edition", "unlocksSource", "note"]}
    b.setdefault("edition", "06:30")
    b["date"] = today
    for k in LISTS:
        if not isinstance(b.get(k), list):
            b[k] = []
    b["tldr"] = b["tldr"][:10]
    b["watchlist"] = b["watchlist"][:5]
    b["news"] = b["news"][:7]

    def fix(obj: dict) -> None:
        if "impact" in obj and obj["impact"] not in IMPACTS:
            obj["impact"] = "neu"
        if "sentiment" in obj and obj["sentiment"] not in IMPACTS:
            obj["sentiment"] = "neu"
        if "confidence" in obj and obj["confidence"] not in CONFS:
            obj["confidence"] = "unconfirmed"
        for s in obj.get("sources", []) or []:
            s["url"] = _safe_url(s.get("url"))

    for k in LISTS:
        for obj in b[k]:
            if isinstance(obj, dict):
                fix(obj)
    if isinstance(b.get("unlocksSource"), dict):
        b["unlocksSource"]["url"] = _safe_url(b["unlocksSource"].get("url"))
    return b


def inject_market(b: dict, prio: list[dict], cfg: dict) -> None:
    """Les chiffres viennent de CoinGecko, jamais du modèle."""
    written = {m.get("symbol"): m for m in b.get("market", []) if isinstance(m, dict)}
    out = []
    for p in prio:
        m = written.get(p["symbol"], {"symbol": p["symbol"], "sentiment": "neu", "driver": "", "events": [], "watch": []})
        m.update({k: p[k] for k in ("name", "price", "change24h", "change7d", "volume")})
        if p.get("lastUpdated"):
            t = datetime.fromisoformat(p["lastUpdated"].replace("Z", "+00:00")).astimezone(now_local(cfg).tzinfo)
            m["asOf"] = t.strftime("%d/%m %H:%M")
        else:
            m["asOf"] = "Donnée indisponible"
        m["source"] = "CoinGecko"
        out.append(m)
    b["market"] = out


def publish(b: dict) -> None:
    write_json(BRIEF_DIR / f"{b['date']}.json", b)
    idx = read_json(DATA_DIR / "index.json", {"dates": []}) or {"dates": []}
    dates = sorted(set(idx.get("dates", []) + [b["date"]]), reverse=True)[:60]
    write_json(DATA_DIR / "index.json", {"dates": dates, "latest": dates[0]})


def main() -> int:
    cfg = load_config()
    force = "--force" in sys.argv
    if not force and not in_window(cfg):
        return 0
    today = now_local(cfg).date().isoformat()
    state = load_state()
    try:
        ctx, prio = gather_context(cfg, state)
        raw = call_claude(cfg, ctx, today)
        b = sanitize(raw, today)
        inject_market(b, prio, cfg)
        b["generatedAt"] = b["updatedAt"] = now_utc_iso()
        publish(b)
        state["digest_queue"] = []  # intégrées au briefing
        save_state(state)
        notify.send(notify.format_briefing(b, cfg.get("dashboard_url", "")))
        log.info("Briefing %s publié.", today)
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("Échec du briefing")
        notify.send(f"⚠️ Le briefing de 06:30 a échoué : {notify.esc(str(e))[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
