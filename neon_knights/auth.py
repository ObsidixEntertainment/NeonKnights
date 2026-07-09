from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import json
import os
import re
import time
from contextlib import contextmanager
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from .models import Character
from .world import ANCESTRIES, GEAR


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_CHARACTERS_PER_ACCOUNT = 2
PASSWORD_ITERATIONS = 200_000


METADATA = MetaData()

USERS = Table(
    "users",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("password_salt", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("email_verified", Boolean, nullable=False, server_default=text("false")),
    Column("is_admin", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", Integer, nullable=False),
)

CHARACTERS = Table(
    "characters",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("slot", Integer, nullable=False),
    Column("name", String(32), nullable=False),
    Column("ancestry", String(64), nullable=False),
    Column("state_json", Text, nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("updated_at", Integer, nullable=False),
    UniqueConstraint("user_id", "slot", name="uq_characters_user_slot"),
    UniqueConstraint("user_id", "name", name="uq_characters_user_name"),
)

EMAIL_CODES = Table(
    "email_codes",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("purpose", String(64), nullable=False),
    Column("code", String(32), nullable=False),
    Column("created_at", Integer, nullable=False),
    Column("expires_at", Integer, nullable=False),
    Column("used_at", Integer),
)


@dataclass(frozen=True)
class User:
    id: int
    email: str
    email_verified: bool
    is_admin: bool


@dataclass(frozen=True)
class CharacterSummary:
    id: int
    slot: int
    name: str
    ancestry: str
    location: str


@dataclass(frozen=True)
class EmailCodeSummary:
    email: str
    purpose: str
    code: str
    created_at: int
    expires_at: int
    used_at: int | None


@dataclass(frozen=True)
class ResetSummary:
    users: int
    characters: int
    email_codes: int


def format_reset_summary(summary: ResetSummary) -> str:
    return (
        "All users, characters, and email codes were reset. "
        f"Removed users={summary.users}, characters={summary.characters}, email_codes={summary.email_codes}."
    )


class AuthStore:
    def __init__(self, db_path: str | Path | None = None, database_url: str | None = None):
        configured_url = database_url or os.environ.get("DATABASE_URL") or os.environ.get("NEON_KNIGHTS_DATABASE_URL")
        self.db_path: Path | None = None
        if configured_url:
            self.engine = create_engine(normalize_database_url(configured_url), future=True, pool_pre_ping=True)
        else:
            self.db_path = Path(db_path or os.environ.get("NEON_KNIGHTS_DB", "neon_knights.sqlite3"))
            if self.db_path.parent != Path("."):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{self.db_path.resolve().as_posix()}", future=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def init_db(self) -> None:
        METADATA.create_all(self.engine)
        self.ensure_legacy_columns()

    def close(self) -> None:
        self.engine.dispose()

    def ensure_legacy_columns(self) -> None:
        inspector = inspect(self.engine)
        if not inspector.has_table("users"):
            return
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        with self.connect() as db:
            if "email_verified" not in user_columns:
                db.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false"))
            if "is_admin" not in user_columns:
                db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false"))

    def create_user(self, email: str, password: str, *, is_admin: bool = False, email_verified: bool = False) -> User:
        email = normalize_email(email)
        validate_password(password)
        salt, password_hash = hash_password(password)
        now = int(time.time())
        try:
            with self.connect() as db:
                result = db.execute(
                    insert(USERS).values(
                        email=email,
                        password_salt=salt,
                        password_hash=password_hash,
                        email_verified=email_verified,
                        is_admin=is_admin,
                        created_at=now,
                    )
                )
                return User(
                    id=int(result.inserted_primary_key[0]),
                    email=email,
                    email_verified=email_verified,
                    is_admin=is_admin,
                )
        except IntegrityError as exc:
            raise ValueError("That email is already signed up.") from exc

    def verify_user(self, email: str, password: str) -> User:
        email = normalize_email(email)
        with self.connect() as db:
            row = db.execute(select(USERS).where(USERS.c.email == email)).mappings().first()
        if row is None or not verify_password(password, row["password_salt"], row["password_hash"]):
            raise ValueError("Email or password is incorrect.")
        return user_from_row(row)

    def set_password(self, user_id: int, password: str) -> User:
        validate_password(password)
        salt, password_hash = hash_password(password)
        with self.connect() as db:
            db.execute(
                update(USERS)
                .where(USERS.c.id == user_id)
                .values(password_salt=salt, password_hash=password_hash)
            )
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        return user

    def get_user(self, user_id: int) -> User | None:
        with self.connect() as db:
            row = db.execute(select(USERS).where(USERS.c.id == user_id)).mappings().first()
        return user_from_row(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        email = normalize_email(email)
        with self.connect() as db:
            row = db.execute(select(USERS).where(USERS.c.email == email)).mappings().first()
        return user_from_row(row) if row else None

    def admin_count(self) -> int:
        with self.connect() as db:
            count = db.execute(select(func.count()).select_from(USERS).where(USERS.c.is_admin.is_(True))).scalar_one()
        return int(count)

    def promote_admin(self, user_id: int) -> User:
        with self.connect() as db:
            db.execute(update(USERS).where(USERS.c.id == user_id).values(is_admin=True))
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        return user

    def set_email_verified(self, user_id: int) -> User:
        with self.connect() as db:
            db.execute(update(USERS).where(USERS.c.id == user_id).values(email_verified=True))
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        return user

    def create_email_code(self, user_id: int, purpose: str = "verify-email", ttl_seconds: int = 900) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = int(time.time())
        with self.connect() as db:
            db.execute(
                update(EMAIL_CODES)
                .where(
                    EMAIL_CODES.c.user_id == user_id,
                    EMAIL_CODES.c.purpose == purpose,
                    EMAIL_CODES.c.used_at.is_(None),
                )
                .values(used_at=now)
            )
            db.execute(
                insert(EMAIL_CODES).values(
                    user_id=user_id,
                    purpose=purpose,
                    code=code,
                    created_at=now,
                    expires_at=now + ttl_seconds,
                )
            )
        return code

    def verify_email_code(self, user_id: int, code: str, purpose: str = "verify-email") -> User:
        code = " ".join(code.strip().split())
        now = int(time.time())
        with self.connect() as db:
            row = db.execute(
                select(EMAIL_CODES.c.id)
                .where(
                    EMAIL_CODES.c.user_id == user_id,
                    EMAIL_CODES.c.purpose == purpose,
                    EMAIL_CODES.c.code == code,
                    EMAIL_CODES.c.used_at.is_(None),
                    EMAIL_CODES.c.expires_at >= now,
                )
                .order_by(EMAIL_CODES.c.created_at.desc(), EMAIL_CODES.c.id.desc())
                .limit(1)
            ).mappings().first()
            if row is None:
                raise ValueError("That email code is incorrect or expired.")
            db.execute(update(EMAIL_CODES).where(EMAIL_CODES.c.id == int(row["id"])).values(used_at=now))
            if purpose == "verify-email":
                db.execute(update(USERS).where(USERS.c.id == user_id).values(email_verified=True))
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("User not found.")
        return user

    def list_users(self) -> list[User]:
        with self.connect() as db:
            rows = db.execute(select(USERS).order_by(USERS.c.created_at.asc())).mappings().all()
        return [user_from_row(row) for row in rows]

    def list_email_codes(self, email: str | None = None, limit: int = 10) -> list[EmailCodeSummary]:
        statement = (
            select(
                USERS.c.email,
                EMAIL_CODES.c.purpose,
                EMAIL_CODES.c.code,
                EMAIL_CODES.c.created_at,
                EMAIL_CODES.c.expires_at,
                EMAIL_CODES.c.used_at,
            )
            .select_from(EMAIL_CODES.join(USERS, USERS.c.id == EMAIL_CODES.c.user_id))
            .order_by(EMAIL_CODES.c.created_at.desc(), EMAIL_CODES.c.id.desc())
            .limit(limit)
        )
        if email:
            statement = statement.where(USERS.c.email == normalize_email(email))
        with self.connect() as db:
            rows = db.execute(statement).mappings().all()
        return [
            EmailCodeSummary(
                email=str(row["email"]),
                purpose=str(row["purpose"]),
                code=str(row["code"]),
                created_at=int(row["created_at"]),
                expires_at=int(row["expires_at"]),
                used_at=int(row["used_at"]) if row["used_at"] is not None else None,
            )
            for row in rows
        ]

    def reset_all_accounts(self) -> ResetSummary:
        with self.connect() as db:
            users = int(db.execute(select(func.count()).select_from(USERS)).scalar_one())
            characters = int(db.execute(select(func.count()).select_from(CHARACTERS)).scalar_one())
            email_codes = int(db.execute(select(func.count()).select_from(EMAIL_CODES)).scalar_one())
            db.execute(delete(EMAIL_CODES))
            db.execute(delete(CHARACTERS))
            db.execute(delete(USERS))
            self.reset_sequences(db)
        return ResetSummary(users=users, characters=characters, email_codes=email_codes)

    def reset_sequences(self, db: Connection) -> None:
        dialect = self.engine.dialect.name
        if dialect == "sqlite":
            row = db.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'")
            ).first()
            if row:
                db.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('users', 'characters', 'email_codes')"))
        elif dialect == "postgresql":
            for sequence in ("users_id_seq", "characters_id_seq", "email_codes_id_seq"):
                db.execute(text(f"ALTER SEQUENCE IF EXISTS {sequence} RESTART WITH 1"))

    def list_characters(self, user_id: int) -> list[CharacterSummary]:
        with self.connect() as db:
            rows = db.execute(
                select(
                    CHARACTERS.c.id,
                    CHARACTERS.c.slot,
                    CHARACTERS.c.name,
                    CHARACTERS.c.ancestry,
                    CHARACTERS.c.state_json,
                )
                .where(CHARACTERS.c.user_id == user_id)
                .order_by(CHARACTERS.c.slot.asc())
            ).mappings().all()
        summaries = []
        for row in rows:
            state = json.loads(row["state_json"])
            summaries.append(
                CharacterSummary(
                    id=int(row["id"]),
                    slot=int(row["slot"]),
                    name=str(row["name"]),
                    ancestry=str(row["ancestry"]),
                    location=str(state.get("location", "redline-station")),
                )
            )
        return summaries

    def create_character(self, user_id: int, name: str, ancestry: str) -> tuple[int, Character]:
        name = normalize_name(name)
        ancestry = ancestry.strip().lower()
        if ancestry not in ANCESTRIES:
            raise ValueError("Choose a listed ancestry.")

        summaries = self.list_characters(user_id)
        if len(summaries) >= MAX_CHARACTERS_PER_ACCOUNT:
            raise ValueError("Each email account can hold two characters right now.")
        if any(summary.name.lower() == name.lower() for summary in summaries):
            raise ValueError("That character name is already used on this account.")

        used_slots = {summary.slot for summary in summaries}
        slot = next(index for index in range(1, MAX_CHARACTERS_PER_ACCOUNT + 1) if index not in used_slots)
        character = Character(name=name, ancestry=ancestry)
        now = int(time.time())
        try:
            with self.connect() as db:
                result = db.execute(
                    insert(CHARACTERS).values(
                        user_id=user_id,
                        slot=slot,
                        name=name,
                        ancestry=ancestry,
                        state_json=character_to_json(character),
                        created_at=now,
                        updated_at=now,
                    )
                )
                return int(result.inserted_primary_key[0]), character
        except IntegrityError as exc:
            raise ValueError("That character name is already used on this account.") from exc

    def load_character(self, user_id: int, character_id: int) -> Character:
        with self.connect() as db:
            row = db.execute(
                select(CHARACTERS).where(CHARACTERS.c.user_id == user_id, CHARACTERS.c.id == character_id)
            ).mappings().first()
        if row is None:
            raise ValueError("Character not found.")
        return character_from_json(str(row["state_json"]))

    def save_character(self, user_id: int, character_id: int, character: Character) -> None:
        now = int(time.time())
        with self.connect() as db:
            db.execute(
                update(CHARACTERS)
                .where(CHARACTERS.c.user_id == user_id, CHARACTERS.c.id == character_id)
                .values(
                    name=character.name,
                    ancestry=character.ancestry,
                    state_json=character_to_json(character),
                    updated_at=now,
                ),
            )


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    return email


def normalize_database_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def user_from_row(row: Mapping[str, Any]) -> User:
    return User(
        id=int(row["id"]),
        email=str(row["email"]),
        email_verified=bool(row["email_verified"]),
        is_admin=bool(row["is_admin"]),
    )


def normalize_name(name: str) -> str:
    name = " ".join(name.strip().split())
    if not name:
        raise ValueError("Handle is required.")
    if len(name) > 32:
        raise ValueError("Handle must be 32 characters or fewer.")
    return name


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")


def hash_password(password: str) -> tuple[str, str]:
    salt_bytes = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, PASSWORD_ITERATIONS)
    return encode_bytes(salt_bytes), encode_bytes(digest)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    salt_bytes = decode_bytes(salt)
    expected = decode_bytes(expected_hash)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, PASSWORD_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def character_to_json(character: Character) -> str:
    return json.dumps(
        {
            "name": character.name,
            "ancestry": character.ancestry,
            "location": character.location,
            "credits": character.credits,
            "essence": character.essence,
            "hp": character.hp,
            "max_hp": character.max_hp,
            "faction": character.faction,
            "augments": sorted(character.augments),
            "inventory": sorted(character.inventory),
            "equipment": character.equipment,
            "defeated_enemies": sorted(character.defeated_enemies),
            "tutorial_seen": character.tutorial_seen,
        },
        sort_keys=True,
    )


def character_from_json(payload: str) -> Character:
    state = json.loads(payload)
    equipment = {
        str(slot): str(item)
        for slot, item in dict(state.get("equipment", {})).items()
        if item in GEAR
    }
    character = Character(
        name=str(state["name"]),
        ancestry=str(state["ancestry"]),
        location=str(state.get("location", "redline-station")),
        credits=int(state.get("credits", 1200)),
        essence=int(state.get("essence", 100)),
        hp=int(state.get("hp", 30)),
        max_hp=int(state.get("max_hp", 30)),
        faction=state.get("faction"),
        augments=set(state.get("augments", [])),
        inventory=set(state.get("inventory", ["street-knife", "patchwork-coat"])),
        equipment=equipment or {"weapon": "street-knife", "body": "patchwork-coat"},
        defeated_enemies=set(state.get("defeated_enemies", [])),
        tutorial_seen=bool(state.get("tutorial_seen", False)),
    )
    return character
