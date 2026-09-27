"""Règles de fiabilité appliquées PAR LE CODE, pas laissées au jugement du modèle.

- CONFIRMED  : au moins une source tier 1 (officielle), ou au moins deux sources tier 2
               de domaines différents.
- LIKELY     : une seule source tier 2.
- UNCONFIRMED: seulement des sources tier 3 (agrégateurs, sites secondaires).
- RUMOR      : uniquement des publications sociales non officielles.
Les communiqués sponsorisés ne comptent jamais comme preuve.
"""
from __future__ import annotations

from urllib.parse import urlparse


def _host_path(url: str) -> str:
    try:
        u = urlparse(url)
        return (u.netloc.lower().removeprefix("www.") + u.path.lower())
    except ValueError:
        return ""


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _matches(host_path: str, rule: str) -> bool:
    """« aave.com » couvre aave.com et ses sous-domaines ; « coinbase.com/blog » limite au chemin."""
    rule_host, _, rule_path = rule.lower().partition("/")
    host, _, path = host_path.partition("/")
    host_ok = host == rule_host or host.endswith("." + rule_host)
    return host_ok and path.startswith(rule_path)


def is_sponsored(cfg: dict, url: str) -> bool:
    hp = _host_path(url)
    return any(_matches(hp, r) for r in cfg["source_tiers"].get("sponsored", []))


def tier_for_url(cfg: dict, url: str) -> int:
    """1 = officiel, 2 = média reconnu, 3 = reste, 9 = sponsorisé (jamais une preuve)."""
    if not url:
        return 3
    hp = _host_path(url)
    if any(_matches(hp, r) for r in cfg["source_tiers"].get("sponsored", [])):
        return 9
    if any(_matches(hp, r) for r in cfg["source_tiers"].get("tier1", [])):
        return 1
    if any(_matches(hp, r) for r in cfg["source_tiers"].get("tier2", [])):
        return 2
    return 3


def confidence(items: list[dict]) -> str:
    """Calcule la confiance d'un événement à partir de toutes les sources qui en parlent."""
    usable = [i for i in items if i.get("tier", 3) != 9]
    if not usable:
        return "unconfirmed"
    if any(i.get("tier") == 1 for i in usable):
        return "confirmed"
    t2_domains = {domain_of(i.get("url", "")) or i.get("source") for i in usable if i.get("tier") == 2}
    if len(t2_domains) >= 2:
        return "confirmed"
    if len(t2_domains) == 1:
        return "likely"
    if all(i.get("kind") == "x" for i in usable):
        return "rumor"
    return "unconfirmed"


def can_push_critical(items: list[dict]) -> bool:
    """Une alerte 🚨 CRITICAL n'est envoyée immédiatement que si elle est confirmée."""
    return confidence(items) == "confirmed"
