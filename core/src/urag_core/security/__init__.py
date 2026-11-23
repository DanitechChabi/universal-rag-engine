"""Mots de passe (Argon2id), jetons (ADR-0011) et chiffrement des secrets (ADR-0012)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MIN_PASSWORD_LENGTH = 12


class WeakPasswordError(ValueError):
    pass


class PasswordHasher:
    """Argon2id, paramètres par défaut de argon2-cffi (conformes aux recommandations OWASP)."""

    def __init__(self) -> None:
        self._h = _Argon2()
        # Hachage factice : même coût de calcul pour un compte inconnu (pas d'oracle temporel).
        self._dummy = self._h.hash(secrets.token_hex(16))

    def hash(self, password: str) -> str:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(f"au moins {MIN_PASSWORD_LENGTH} caractères")
        return self._h.hash(password)

    def verify(self, stored_hash: str | None, password: str) -> bool:
        try:
            return self._h.verify(stored_hash or self._dummy, password) and stored_hash is not None
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        return self._h.check_needs_rehash(stored_hash)


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    org_id: uuid.UUID
    session_id: uuid.UUID
    roles: tuple[str, ...]


class InvalidTokenError(Exception):
    pass


class TokenService:
    """Jeton d'accès court (JWT HS256) + jeton de rafraîchissement opaque, stocké haché."""

    ALGORITHM = "HS256"

    def __init__(self, secret: bytes, access_ttl: timedelta, refresh_ttl: timedelta) -> None:
        if len(secret) < 32:
            raise ValueError("la clé de signature doit faire au moins 32 octets")
        self._secret = secret
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

    def issue_access(self, claims: AccessClaims, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        payload = {
            "sub": str(claims.user_id),
            "org": str(claims.org_id),
            "sid": str(claims.session_id),
            "roles": list(claims.roles),
            "iat": now,
            "exp": now + self.access_ttl,
            "typ": "access",
        }
        return jwt.encode(payload, self._secret, algorithm=self.ALGORITHM)

    def verify_access(self, token: str) -> AccessClaims:
        try:
            p = jwt.decode(
                token, self._secret, algorithms=[self.ALGORITHM], options={"require": ["exp", "sub", "org", "sid"]}
            )
        except jwt.PyJWTError as e:
            raise InvalidTokenError(str(e)) from e
        if p.get("typ") != "access":
            raise InvalidTokenError("type de jeton invalide")
        return AccessClaims(uuid.UUID(p["sub"]), uuid.UUID(p["org"]), uuid.UUID(p["sid"]), tuple(p.get("roles", ())))

    @staticmethod
    def new_refresh_token() -> tuple[str, bytes]:
        token = secrets.token_urlsafe(48)
        return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


class SecretBox:
    """AES-256-GCM. Le nonce est aléatoire ; l'organisation et l'usage sont liés (données authentifiées)."""

    def __init__(self, master_key: bytes, key_version: int = 1) -> None:
        if len(master_key) != 32:
            raise ValueError("la clé maîtresse doit faire 32 octets")
        self._aead = AESGCM(master_key)
        self._derive_key = hashlib.sha256(b"urag-derive|" + master_key).digest()
        self.key_version = key_version

    @staticmethod
    def _aad(org_id: uuid.UUID, purpose: str) -> bytes:
        return f"{org_id}|{purpose}".encode()

    def encrypt(self, org_id: uuid.UUID, purpose: str, plaintext: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, self._aead.encrypt(nonce, plaintext, self._aad(org_id, purpose))

    def decrypt(self, org_id: uuid.UUID, purpose: str, nonce: bytes, ciphertext: bytes) -> bytes:
        return self._aead.decrypt(nonce, ciphertext, self._aad(org_id, purpose))

    def derive(self, label: str) -> bytes:
        """Sous-clé dérivée (ex. signature des jetons) : HMAC-SHA256(clé maîtresse, label)."""
        return hmac.new(self._derive_key, label.encode(), hashlib.sha256).digest()


def load_master_key(path: Path) -> bytes:
    data = path.read_bytes().strip()
    key = bytes.fromhex(data.decode()) if len(data) == 64 else data
    if len(key) != 32:
        raise ValueError("clé maîtresse invalide : 32 octets (ou 64 caractères hexadécimaux) attendus")
    return key


def generate_master_key(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_hex(32))
