"""Consommation des modèles et plafonds (docs/AI_MODELS.md §2.4).

Chaque appel est enregistré dans ``usage_records`` (jetons, coût estimé, local ou externe). Les
plafonds (``usage_limits``, par jour ou par mois, pour l'organisation ou un utilisateur) portent sur
la consommation **externe** : au-delà, les modèles externes sont écartés si ``disable_on_exceed`` ;
une alerte est émise à partir de ``alert_ratio`` (80 % par défaut).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text

from ..ai import ChatResult


@dataclass(frozen=True)
class LimitStatus:
    period: str
    scope: str  # « organisation » ou « utilisateur »
    used_tokens: int
    used_cost: float
    max_tokens: int | None
    max_cost: float | None
    ratio: float  # part consommée du plafond le plus proche (0 à 1+)
    alert: bool
    exceeded: bool
    blocks_external: bool


def record_usage(conn: Connection, org_id: uuid.UUID, user_id: uuid.UUID | None, result: ChatResult) -> None:
    model = result.model
    if model is None:
        return
    conn.execute(
        text("""
        INSERT INTO usage_records (org_id, user_id, model_id, purpose, locality, tokens_in, tokens_out, cost_estimate)
        VALUES (:o, :u, :m, 'chat', CAST(:loc AS model_locality), :ti, :to, :c)"""),
        {
            "o": org_id,
            "u": user_id,
            "m": model.db_id,
            "loc": model.locality,
            "ti": result.tokens_in,
            "to": result.tokens_out,
            "c": model.cost(result.tokens_in, result.tokens_out),
        },
    )


def limits_status(conn: Connection, org_id: uuid.UUID, user_id: uuid.UUID | None) -> list[LimitStatus]:
    """État des plafonds applicables (organisation et, s'il en a, l'utilisateur)."""
    rows = conn.execute(
        text("""
        SELECT l.period, l.user_id, l.max_tokens, l.max_cost, l.alert_ratio, l.disable_on_exceed,
               coalesce(sum(r.tokens_in + r.tokens_out), 0) AS tokens, coalesce(sum(r.cost_estimate), 0) AS cost
        FROM usage_limits l
        LEFT JOIN usage_records r ON r.org_id = l.org_id AND r.locality = 'external'
             AND (l.user_id IS NULL OR r.user_id = l.user_id)
             AND r.created_at >= date_trunc(CASE l.period WHEN 'day' THEN 'day' ELSE 'month' END, now())
        WHERE l.user_id IS NULL OR l.user_id = :u
        GROUP BY l.id"""),
        {"u": user_id},
    ).all()
    out = []
    for r in rows:
        ratios = []
        if r.max_tokens:
            ratios.append(r.tokens / r.max_tokens)
        if r.max_cost:
            ratios.append(float(r.cost) / float(r.max_cost))
        ratio = max(ratios, default=0.0)
        exceeded = ratio >= 1.0
        out.append(
            LimitStatus(
                period=r.period,
                scope="utilisateur" if r.user_id else "organisation",
                used_tokens=int(r.tokens),
                used_cost=float(r.cost),
                max_tokens=r.max_tokens,
                max_cost=float(r.max_cost) if r.max_cost is not None else None,
                ratio=round(ratio, 4),
                alert=ratio >= r.alert_ratio,
                exceeded=exceeded,
                blocks_external=exceeded and r.disable_on_exceed,
            )
        )
    return out


def external_allowed(conn: Connection, org_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
    return not any(s.blocks_external for s in limits_status(conn, org_id, user_id))
