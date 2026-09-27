"""Surveillance en continu (lancée toutes les 30 min par GitHub Actions).

1. Récupère les nouveautés : flux RSS, comptes X officiels, mouvements de prix anormaux.
2. Les fait trier par un petit modèle (CRITICAL / IMPORTANT / NORMAL).
3. Applique les règles de fiabilité du code : une alerte CRITICAL non confirmée est rétrogradée.
4. Envoie les CRITICAL tout de suite (avec un plafond quotidien), regroupe les IMPORTANT
   dans deux récaps (12:30 et 18:30), et ajoute le tout au briefing du jour (rubrique Breaking).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta

import anthropic

from . import collectors, notify, reliability
from .common import BRIEF_DIR, extract_json, load_config, load_state, log, now_local, now_utc_iso, read_json, read_prompt, save_state, write_json

LEVEL_RANK = {"normal": 0, "important": 1, "critical": 2}


def _hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def in_quiet_hours(cfg: dict, now: datetime) -> bool:
    q = cfg["alerts"]["quiet_hours"]
    start, end = _hhmm(q["start"]), _hhmm(q["end"])
    cur = (now.hour, now.minute)
    return cur >= start or cur < end


def digest_slot(cfg: dict, now: datetime) -> str | None:
    for t in cfg["alerts"]["digest_times"]:
        h, m = _hhmm(t)
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if abs(now - slot) <= timedelta(minutes=16):
            return t
    return None


def classify(cfg: dict, items: list[dict], state: dict) -> list[dict]:
    client = anthropic.Anthropic()
    known = {}
    for r in state["recent"]:
        if r.get("cluster"):
            known[r["cluster"]] = r.get("title", "")[:120]
    payload = {
        "clusters_existants": [{"cluster": k, "exemple": v} for k, v in list(known.items())[-40:]],
        "elements": [{k: i.get(k) for k in ("id", "kind", "title", "summary", "source", "tier", "xRole", "asset")} for i in items],
    }
    resp = client.messages.create(
        model=cfg["models"]["monitor"],
        max_tokens=4000,
        system=read_prompt("monitor_system.md"),
        messages=[{"role": "user", "content": "Réutilise un cluster existant si l'événement est le même.\n<donnees_non_fiables>\n" + json.dumps(payload, ensure_ascii=False) + "\n</donnees_non_fiables>"}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    out = extract_json(text)
    return out if isinstance(out, list) else []


def build_alerts(cfg: dict, items: list[dict], classified: list[dict], state: dict, now: datetime) -> list[dict]:
    by_id = {i["id"]: i for i in items}
    clusters: dict[str, list[dict]] = {}
    for c in classified:
        it = by_id.get(c.get("id"))
        if not it:
            continue
        it["cluster"] = (c.get("cluster") or it["id"])[:60]
        state["recent"].append({k: it.get(k) for k in ("id", "kind", "title", "url", "source", "tier", "xRole", "cluster", "ts")})
        if c.get("level") in ("important", "critical"):
            clusters.setdefault(it["cluster"], []).append({**c, **{"_item": it}})

    alerts = []
    for cluster, group in clusters.items():
        level = max((g["level"] for g in group), key=lambda l: LEVEL_RANK[l])
        related = [r for r in state["recent"] if r.get("cluster") == cluster]
        conf = reliability.confidence(related)
        note = ""
        if level == "critical" and not reliability.can_push_critical(related):
            level, note = "important", " (en attente de confirmation)"
        previous = state["alerted"].get(cluster)
        if previous and LEVEL_RANK[previous] >= LEVEL_RANK[level]:
            continue  # déjà signalé à ce niveau : pas de doublon
        state["alerted"][cluster] = level
        first = group[0]
        alerts.append({
            "id": f"{cluster}:{now.date().isoformat()}",
            "level": level,
            "time": now.strftime("%H:%M"),
            "title": (first.get("title") or first["_item"]["title"]) + note,
            "summary": first.get("summary", ""),
            "assets": first.get("assets") or [],
            "confidence": conf,
            "sources": [{"name": r.get("source"), "url": r.get("url")} for r in related if r.get("tier") != 9][:3],
        })
    return alerts


def append_breaking(alerts: list[dict], today: str) -> None:
    path = BRIEF_DIR / f"{today}.json"
    b = read_json(path)
    if not b:
        return  # avant 06:30 : ces alertes seront reprises dans le briefing du matin
    existing = {x.get("id") for x in b.get("breaking", [])}
    for a in alerts:
        if a["id"] not in existing:
            b.setdefault("breaking", []).insert(0, {k: a[k] for k in ("id", "level", "time", "title", "summary", "confidence", "sources")})
    b["breaking"] = b["breaking"][:20]
    b["updatedAt"] = now_utc_iso()
    write_json(path, b)


def main() -> int:
    cfg = load_config()
    state = load_state()
    state.setdefault("alerted", {})
    now = now_local(cfg)
    today = now.date().isoformat()
    sent = state["sent"].setdefault(today, {"critical": 0, "digests": []})
    if len(state["alerted"]) > 300:
        state["alerted"] = dict(list(state["alerted"].items())[-200:])

    top = collectors.coingecko_top100()
    items = [i for i in collectors.rss_items(cfg, since_hours=6) + collectors.x_posts(cfg, state) if i["id"] not in state["seen"]]
    for i in items:
        state["seen"][i["id"]] = time.time()

    alerts: list[dict] = []
    for a in collectors.price_anomalies(cfg, top):
        if a["id"] in state["seen"]:
            continue
        state["seen"][a["id"]] = time.time()
        alerts.append({**a, "time": now.strftime("%H:%M"), "confidence": "confirmed", "sources": [{"name": "CoinGecko", "url": a["url"]}]})

    if items:
        try:
            classified = classify(cfg, items, state)
            alerts += build_alerts(cfg, items, classified, state, now)
        except Exception as e:  # noqa: BLE001
            log.warning("Tri impossible ce tour-ci : %s", e)

    quiet = in_quiet_hours(cfg, now)
    for a in alerts:
        if a["level"] == "critical" and sent["critical"] < cfg["alerts"]["max_critical_per_day"]:
            if notify.send(notify.format_alert(a)):
                sent["critical"] += 1
        else:
            state["digest_queue"].append({**a, "digested": False})

    slot = digest_slot(cfg, now)
    pending = [q for q in state["digest_queue"] if not q.get("digested")]
    if slot and slot not in sent["digests"] and pending and not quiet:
        if notify.send(notify.format_digest(pending), silent=True):
            for q in pending:
                q["digested"] = True
            sent["digests"].append(slot)

    if alerts:
        append_breaking(alerts, today)
    state["digest_queue"] = state["digest_queue"][-100:]
    save_state(state)
    log.info("Tour terminé : %d nouveautés, %d alertes.", len(items), len(alerts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
