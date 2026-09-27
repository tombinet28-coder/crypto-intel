"""Notifications push via un bot Telegram (gratuit, notification native sur le téléphone).

Le bot ne fait qu'ENVOYER des messages à TON chat. Il n'écoute aucune commande :
personne ne peut le piloter à distance.
"""
from __future__ import annotations

import html
import os

import requests

from .common import log

MAX_LEN = 3900  # limite Telegram : 4096 caractères


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def send(text_html: str, *, silent: bool = False) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.info("Telegram non configuré : message non envoyé.")
        return False
    if len(text_html) > MAX_LEN:
        text_html = text_html[: MAX_LEN - 20] + "\n…"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": silent,
            },
            timeout=20,
        )
        if not r.ok:
            log.warning("Telegram a refusé le message : %s", r.text[:200])
        return r.ok
    except requests.RequestException as e:
        log.warning("Telegram injoignable : %s", e)
        return False


CONF_LABEL = {"confirmed": "🟢 Confirmé", "likely": "🟡 Probable", "unconfirmed": "🟠 Non confirmé", "rumor": "🔴 Rumeur"}
IMPACT_DOT = {"pos": "🟢", "neu": "🟡", "neg": "🔴"}


def format_alert(a: dict) -> str:
    head = "🚨 <b>CRITICAL</b>" if a["level"] == "critical" else "🔔 <b>IMPORTANT</b>"
    lines = [f"{head} — {esc(a.get('time', ''))}", f"<b>{esc(a['title'])}</b>"]
    if a.get("summary"):
        lines.append(esc(a["summary"]))
    if a.get("assets"):
        lines.append("Concerne : " + esc(", ".join(a["assets"])))
    lines.append(CONF_LABEL.get(a.get("confidence", ""), ""))
    for s in (a.get("sources") or [])[:3]:
        if s.get("url", "").startswith(("http://", "https://")):
            lines.append(f'<a href="{esc(s["url"])}">{esc(s.get("name", "source"))}</a>')
    return "\n".join(l for l in lines if l)


def format_digest(alerts: list[dict]) -> str:
    lines = [f"🔔 <b>Récap des alertes importantes</b> ({len(alerts)})", ""]
    for a in alerts[:12]:
        lines.append(f"• <b>{esc(a['title'])}</b> — {CONF_LABEL.get(a.get('confidence', ''), '')}")
        if a.get("summary"):
            lines.append("  " + esc(a["summary"][:220]))
    return "\n".join(lines)


def format_briefing(b: dict, dashboard_url: str) -> str:
    lines = [f"🪙 <b>CRYPTO DAILY — {esc(b.get('edition', '06:30'))}</b>", esc(b.get("date", "")), "", "⚡ <b>TL;DR</b>"]
    for t in b.get("tldr", [])[:10]:
        lines.append(f"{IMPACT_DOT.get(t.get('impact'), '•')} {esc(t.get('text'))}")
    if b.get("watchlist"):
        lines += ["", "👀 <b>À surveiller aujourd'hui</b>"]
        for i, w in enumerate(b["watchlist"][:5], 1):
            lines.append(f"{i}. {IMPACT_DOT.get(w.get('impact'), '')} {esc(w.get('text'))}")
    if dashboard_url:
        lines += ["", f'<a href="{esc(dashboard_url)}">Ouvrir le briefing complet</a>']
    return "\n".join(lines)
