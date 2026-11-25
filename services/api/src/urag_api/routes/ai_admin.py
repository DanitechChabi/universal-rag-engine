"""Administration de l'IA : politique, fournisseurs, modèles, plafonds (docs/AI_MODELS.md §2, phase 5).

Réservé à l'administrateur d'organisation. Les clés d'API sont chiffrées (ADR-0012) et **jamais
renvoyées** : l'API indique seulement si une clé est enregistrée. Toute modification s'applique à
la question suivante (le routeur de l'organisation est reconstruit).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from urag_core.ai import DataKind, ModelSpec
from urag_core.ai.catalog import build_adapter, provider_secret_purpose, read_secret
from urag_core.audit import record
from urag_core.rag import load_policy
from urag_core.usage import external_allowed, limits_status

from ..deps import CAN_ASK, ORG_ADMIN, CurrentUser, get_state, problem, require
from ..state import AppState

router = APIRouter(tags=["intelligence artificielle"])

SUPPORTED = ("ollama", "openai_compatible", "openai", "gemini", "anthropic")
EXTERNAL_KINDS = ("openai", "gemini", "anthropic")


# ------------------------------------------------------------------ vue d'ensemble


@router.get("/admin/ai")
def overview(user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    with state.db.org(user.org_id) as conn:
        policy = load_policy(conn, user.org_id)
        providers = conn.execute(
            text("""SELECT id, kind::text AS kind, name, endpoint, locality::text AS locality, enabled,
                           secret_id IS NOT NULL AS key_configured FROM ai_providers ORDER BY name""")
        ).all()
        models = conn.execute(
            text("""SELECT m.id, m.provider_id, m.name, m.priority, m.enabled, m.available, m.last_checked_at,
                           m.temperature, m.max_output_tokens, m.context_window, m.max_concurrency,
                           m.input_cost_per_mtok, m.output_cost_per_mtok, p.locality::text AS locality
                    FROM ai_models m JOIN ai_providers p ON p.id = m.provider_id
                    WHERE m.purpose = 'chat' ORDER BY m.priority, m.name""")
        ).all()
        limits = conn.execute(
            text("""SELECT id, period, max_tokens, max_cost, alert_ratio, disable_on_exceed
                    FROM usage_limits WHERE user_id IS NULL ORDER BY period""")
        ).all()
        status = limits_status(conn, user.org_id, None)
        usage = conn.execute(
            text("""SELECT coalesce(m.name, 'modèle de l''installation') AS model, r.locality::text AS locality,
                           count(*) AS calls, sum(r.tokens_in) AS tokens_in, sum(r.tokens_out) AS tokens_out,
                           sum(r.cost_estimate) AS cost
                    FROM usage_records r LEFT JOIN ai_models m ON m.id = r.model_id
                    WHERE r.created_at >= date_trunc('month', now())
                    GROUP BY 1, 2 ORDER BY 1""")
        ).all()
    return {
        "policy": {
            "mode": policy.mode,
            "allow_external_questions": policy.allow_external_questions,
            "allow_external_documents": policy.allow_external_documents,
            "allow_fallback_to_external": policy.allow_fallback_to_external,
            "notify_user_on_external": policy.notify_user_on_external,
        },
        "providers": [dict(r._mapping) | {"id": str(r.id)} for r in providers],
        "models": [
            dict(r._mapping)
            | {
                "id": str(r.id),
                "provider_id": str(r.provider_id),
                "input_cost_per_mtok": float(r.input_cost_per_mtok) if r.input_cost_per_mtok is not None else None,
                "output_cost_per_mtok": float(r.output_cost_per_mtok) if r.output_cost_per_mtok is not None else None,
            }
            for r in models
        ],
        "limits": [
            dict(r._mapping) | {"id": str(r.id), "max_cost": float(r.max_cost) if r.max_cost is not None else None}
            for r in limits
        ],
        "limits_status": [s.__dict__ for s in status],
        "usage_month": [dict(r._mapping) | {"cost": float(r.cost) if r.cost is not None else None} for r in usage],
        "supported_kinds": list(SUPPORTED),
    }


# ------------------------------------------------------------------ politique


class PolicyIn(BaseModel):
    mode: Literal["local_only", "hybrid", "cloud_allowed"]
    allow_external_questions: bool = False
    allow_external_documents: bool = False
    allow_fallback_to_external: bool = False
    notify_user_on_external: bool = True


@router.put("/admin/ai/policy", status_code=204)
def set_policy(body: PolicyIn, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    """Scénario 15 : ``local_only`` coupe tout accès externe, à effet immédiat."""
    try:
        with state.db.org(user.org_id) as conn:
            conn.execute(
                text("""
                INSERT INTO ai_policies (org_id, mode, allow_external_questions, allow_external_documents,
                                         allow_fallback_to_external, notify_user_on_external, updated_at)
                VALUES (:o, CAST(:m AS ai_policy_mode), :q, :d, :f, :n, now())
                ON CONFLICT (org_id) DO UPDATE SET mode = EXCLUDED.mode,
                    allow_external_questions = EXCLUDED.allow_external_questions,
                    allow_external_documents = EXCLUDED.allow_external_documents,
                    allow_fallback_to_external = EXCLUDED.allow_fallback_to_external,
                    notify_user_on_external = EXCLUDED.notify_user_on_external, updated_at = now()"""),
                {
                    "o": user.org_id,
                    "m": body.mode,
                    "q": body.allow_external_questions,
                    "d": body.allow_external_documents,
                    "f": body.allow_fallback_to_external,
                    "n": body.notify_user_on_external,
                },
            )
            record(conn, user.org_id, "ai.policy", actor=user.user_id, details=body.model_dump())
    except IntegrityError as e:
        raise problem(
            422,
            "ai.policy_incoherent",
            "Politique incohérente : en mode « local uniquement », aucun envoi vers l'extérieur n'est possible",
        ) from e


# ------------------------------------------------------------------ fournisseurs


def _http_url(value: str | None) -> str | None:
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("adresse http(s) attendue")
    return value


class ProviderIn(BaseModel):
    kind: Literal["ollama", "openai_compatible", "openai", "gemini", "anthropic"]
    name: str = Field(min_length=1, max_length=120)
    endpoint: str | None = Field(default=None, max_length=500)
    locality: Literal["local", "external"] | None = None  # imposé pour Ollama, OpenAI, Gemini et Anthropic
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool = True

    _url = field_validator("endpoint")(lambda cls, v: _http_url(v))  # noqa: E731


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    endpoint: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None

    _url = field_validator("endpoint")(lambda cls, v: _http_url(v))  # noqa: E731


def _store_key(conn, state: AppState, org_id: uuid.UUID, provider_id: uuid.UUID, api_key: str) -> uuid.UUID:
    if state.secrets is None:
        raise problem(503, "secrets.unavailable", "Clé maîtresse absente : impossible d'enregistrer une clé d'API")
    nonce, ciphertext = state.secrets.encrypt(org_id, provider_secret_purpose(provider_id), api_key.encode())
    return conn.execute(
        text("""INSERT INTO secrets (org_id, purpose, key_version, nonce, ciphertext)
                VALUES (:o, :p, :v, :n, :c) RETURNING id"""),
        {
            "o": org_id,
            "p": provider_secret_purpose(provider_id),
            "v": state.secrets.key_version,
            "n": nonce,
            "c": ciphertext,
        },
    ).scalar_one()


@router.post("/admin/ai/providers", status_code=201)
def create_provider(
    body: ProviderIn, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    if body.kind == "ollama":
        locality = "local"
    elif body.kind in EXTERNAL_KINDS:
        locality = "external"
    else:
        locality = body.locality or "local"
    pid = uuid.uuid4()
    try:
        with state.db.org(user.org_id) as conn:
            conn.execute(
                text("""INSERT INTO ai_providers (id, org_id, kind, name, endpoint, locality, enabled)
                        VALUES (:i, :o, CAST(:k AS provider_kind), :n, :e, CAST(:l AS model_locality), :en)"""),
                {
                    "i": pid,
                    "o": user.org_id,
                    "k": body.kind,
                    "n": body.name,
                    "e": body.endpoint,
                    "l": locality,
                    "en": body.enabled,
                },
            )
            if body.api_key:
                sid = _store_key(conn, state, user.org_id, pid, body.api_key)
                conn.execute(text("UPDATE ai_providers SET secret_id = :s WHERE id = :i"), {"s": sid, "i": pid})
            record(
                conn,
                user.org_id,
                "ai.provider.create",
                actor=user.user_id,
                target_type="ai_provider",
                target_id=str(pid),
                details={"kind": body.kind, "locality": locality},
            )
    except IntegrityError as e:
        raise problem(409, "ai.provider_exists", "Un fournisseur porte déjà ce nom") from e
    state.routers.invalidate(user.org_id)
    return {"id": str(pid), "locality": locality}


@router.patch("/admin/ai/providers/{provider_id}", status_code=204)
def update_provider(
    provider_id: uuid.UUID,
    body: ProviderPatch,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    with state.db.org(user.org_id) as conn:
        old = conn.execute(text("SELECT secret_id FROM ai_providers WHERE id = :i"), {"i": provider_id}).first()
        if old is None:
            raise problem(404, "ai.provider_not_found", "Fournisseur introuvable")
        for column in ("name", "endpoint", "enabled"):
            value = getattr(body, column)
            if value is not None:
                conn.execute(
                    text(f"UPDATE ai_providers SET {column} = :v WHERE id = :i"), {"v": value, "i": provider_id}
                )
        if body.api_key:
            sid = _store_key(conn, state, user.org_id, provider_id, body.api_key)
            conn.execute(text("UPDATE ai_providers SET secret_id = :s WHERE id = :i"), {"s": sid, "i": provider_id})
            if old.secret_id:
                conn.execute(text("DELETE FROM secrets WHERE id = :s"), {"s": old.secret_id})
        record(
            conn,
            user.org_id,
            "ai.provider.update",
            actor=user.user_id,
            target_type="ai_provider",
            target_id=str(provider_id),
            details=body.model_dump(exclude={"api_key"}, exclude_none=True)
            | ({"api_key": "remplacée"} if body.api_key else {}),
        )
    state.routers.invalidate(user.org_id)


@router.delete("/admin/ai/providers/{provider_id}", status_code=204)
def delete_provider(
    provider_id: uuid.UUID, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        old = conn.execute(text("SELECT secret_id FROM ai_providers WHERE id = :i"), {"i": provider_id}).first()
        if old is None:
            raise problem(404, "ai.provider_not_found", "Fournisseur introuvable")
        conn.execute(text("DELETE FROM ai_providers WHERE id = :i"), {"i": provider_id})  # modèles en cascade
        if old.secret_id:
            conn.execute(text("DELETE FROM secrets WHERE id = :s"), {"s": old.secret_id})
        record(
            conn,
            user.org_id,
            "ai.provider.delete",
            actor=user.user_id,
            target_type="ai_provider",
            target_id=str(provider_id),
        )
    state.routers.invalidate(user.org_id)


# ------------------------------------------------------------------ modèles


class ModelIn(BaseModel):
    provider_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    priority: int = 100
    enabled: bool = True
    temperature: float | None = Field(default=0.1, ge=0, le=2)
    max_output_tokens: int | None = Field(default=800, gt=0)
    context_window: int | None = Field(default=8192, gt=0)
    max_concurrency: int = Field(default=2, gt=0, le=64)
    input_cost_per_mtok: float | None = Field(default=None, ge=0)
    output_cost_per_mtok: float | None = Field(default=None, ge=0)


class ModelPatch(BaseModel):
    priority: int | None = None
    enabled: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, gt=0)
    context_window: int | None = Field(default=None, gt=0)
    max_concurrency: int | None = Field(default=None, gt=0, le=64)
    input_cost_per_mtok: float | None = Field(default=None, ge=0)
    output_cost_per_mtok: float | None = Field(default=None, ge=0)


@router.post("/admin/ai/models", status_code=201)
def create_model(body: ModelIn, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)):
    """Le modèle n'est proposé qu'après un test de disponibilité réussi (``available``)."""
    try:
        with state.db.org(user.org_id) as conn:
            if conn.execute(text("SELECT 1 FROM ai_providers WHERE id = :i"), {"i": body.provider_id}).first() is None:
                raise problem(404, "ai.provider_not_found", "Fournisseur introuvable")
            mid = conn.execute(
                text("""
                INSERT INTO ai_models (org_id, provider_id, name, purpose, priority, enabled, temperature,
                    max_output_tokens, context_window, max_concurrency, input_cost_per_mtok, output_cost_per_mtok)
                VALUES (:o, :p, :n, 'chat', :pr, :en, :t, :mo, :cw, :mc, :ic, :oc) RETURNING id"""),
                {
                    "o": user.org_id,
                    "p": body.provider_id,
                    "n": body.name,
                    "pr": body.priority,
                    "en": body.enabled,
                    "t": body.temperature,
                    "mo": body.max_output_tokens,
                    "cw": body.context_window,
                    "mc": body.max_concurrency,
                    "ic": body.input_cost_per_mtok,
                    "oc": body.output_cost_per_mtok,
                },
            ).scalar_one()
            record(
                conn,
                user.org_id,
                "ai.model.create",
                actor=user.user_id,
                target_type="ai_model",
                target_id=str(mid),
                details={"name": body.name},
            )
    except IntegrityError as e:
        raise problem(409, "ai.model_exists", "Ce modèle est déjà déclaré pour ce fournisseur") from e
    state.routers.invalidate(user.org_id)
    return {"id": str(mid)}


@router.patch("/admin/ai/models/{model_id}", status_code=204)
def update_model(
    model_id: uuid.UUID,
    body: ModelPatch,
    user: CurrentUser = Depends(require(*ORG_ADMIN)),
    state: AppState = Depends(get_state),
):
    changes = body.model_dump(exclude_unset=True)
    with state.db.org(user.org_id) as conn:
        if conn.execute(text("SELECT 1 FROM ai_models WHERE id = :i"), {"i": model_id}).first() is None:
            raise problem(404, "ai.model_not_found", "Modèle introuvable")
        for column, value in changes.items():  # colonnes connues (modèle Pydantic), jamais saisies librement
            conn.execute(text(f"UPDATE ai_models SET {column} = :v WHERE id = :i"), {"v": value, "i": model_id})
        record(
            conn,
            user.org_id,
            "ai.model.update",
            actor=user.user_id,
            target_type="ai_model",
            target_id=str(model_id),
            details=changes,
        )
    state.routers.invalidate(user.org_id)


@router.delete("/admin/ai/models/{model_id}", status_code=204)
def delete_model(
    model_id: uuid.UUID, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    with state.db.org(user.org_id) as conn:
        if not conn.execute(text("DELETE FROM ai_models WHERE id = :i"), {"i": model_id}).rowcount:
            raise problem(404, "ai.model_not_found", "Modèle introuvable")
        record(
            conn, user.org_id, "ai.model.delete", actor=user.user_id, target_type="ai_model", target_id=str(model_id)
        )
    state.routers.invalidate(user.org_id)


@router.post("/admin/ai/models/{model_id}/test")
def test_model(
    model_id: uuid.UUID, user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    """Test de disponibilité : le fournisseur répond-il, le modèle existe-t-il (Ollama) ?
    Aucun contenu n'est envoyé : simple vérification de l'accès."""
    with state.db.org(user.org_id) as conn:
        r = conn.execute(
            text("""SELECT m.name, p.id AS provider_id, p.kind::text AS kind, p.endpoint, p.secret_id
                    FROM ai_models m JOIN ai_providers p ON p.id = m.provider_id WHERE m.id = :i"""),
            {"i": model_id},
        ).first()
        if r is None:
            raise problem(404, "ai.model_not_found", "Modèle introuvable")
        key = read_secret(conn, state.secrets, user.org_id, r.secret_id, provider_secret_purpose(r.provider_id))
    try:
        adapter = build_adapter(r.kind, r.endpoint, key)
        ok = adapter.health()
        detail = "fournisseur joignable" if ok else "fournisseur injoignable ou clé refusée"
        if ok and r.kind == "ollama":
            ok = r.name in adapter.available_models()
            detail = "modèle présent sur le serveur" if ok else "modèle absent du serveur Ollama"
        elif ok and r.kind == "anthropic":
            ok = adapter.has_model(r.name)
            detail = "modèle disponible pour cette clé" if ok else "modèle inconnu d'Anthropic pour cette clé"
    except (ValueError, Exception) as e:  # noqa: BLE001 - message sans secret, sans trace technique
        ok, detail = False, f"configuration invalide : {type(e).__name__}"
    with state.db.org(user.org_id) as conn:
        conn.execute(
            text("UPDATE ai_models SET available = :a, last_checked_at = now() WHERE id = :i"),
            {"a": ok, "i": model_id},
        )
        record(
            conn,
            user.org_id,
            "ai.model.test",
            actor=user.user_id,
            target_type="ai_model",
            target_id=str(model_id),
            outcome="success" if ok else "failure",
        )
    state.routers.invalidate(user.org_id)
    return {"available": ok, "detail": detail}


# ------------------------------------------------------------------ plafonds


class LimitIn(BaseModel):
    period: Literal["day", "month"]
    max_tokens: int | None = Field(default=None, gt=0)
    max_cost: float | None = Field(default=None, gt=0)
    alert_ratio: float = Field(default=0.8, gt=0, le=1)
    disable_on_exceed: bool = True


@router.put("/admin/ai/limits", status_code=204)
def set_limits(
    limits: list[LimitIn], user: CurrentUser = Depends(require(*ORG_ADMIN)), state: AppState = Depends(get_state)
):
    """Plafonds de consommation **externe** de l'organisation (remplace les plafonds existants)."""
    if len({x.period for x in limits}) != len(limits):
        raise problem(422, "ai.limits_duplicate", "Un seul plafond par période")
    if any(x.max_tokens is None and x.max_cost is None for x in limits):
        raise problem(422, "ai.limits_empty", "Indiquez un plafond en jetons ou en coût")
    with state.db.org(user.org_id) as conn:
        conn.execute(text("DELETE FROM usage_limits WHERE user_id IS NULL"))
        for x in limits:
            conn.execute(
                text("""INSERT INTO usage_limits (org_id, period, max_tokens, max_cost, alert_ratio, disable_on_exceed)
                        VALUES (:o, :p, :t, :c, :a, :d)"""),
                {
                    "o": user.org_id,
                    "p": x.period,
                    "t": x.max_tokens,
                    "c": x.max_cost,
                    "a": x.alert_ratio,
                    "d": x.disable_on_exceed,
                },
            )
        record(conn, user.org_id, "ai.limits", actor=user.user_id, details={"count": len(limits)})


# ------------------------------------------------------------------ modèles proposés à l'utilisateur


@router.get("/models")
def usable_models(user: CurrentUser = Depends(require(*CAN_ASK)), state: AppState = Depends(get_state)):
    """Modèles que l'utilisateur peut choisir maintenant (scénario 14) : autorisés par la politique
    pour une question avec extraits documentaires, et non bloqués par un plafond."""
    with state.db.org(user.org_id) as conn:
        policy = load_policy(conn, user.org_id)
        allow_external = external_allowed(conn, user.org_id, user.user_id)
    routing = state.routers.get(user.org_id) or state.router
    models: list[ModelSpec] = routing.candidates(policy, {DataKind.QUESTION, DataKind.DOCUMENTS}, None, allow_external)
    return {
        "items": [{"id": m.id, "name": m.name, "locality": m.locality} for m in models],
        "external_blocked_by_limit": not allow_external,
        "notify_on_external": policy.notify_user_on_external,
    }
