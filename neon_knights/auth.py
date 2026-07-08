from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .models import Character
from .world import ANCESTRIES, GEAR


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_CHARACTERS_PER_ACCOUNT = 2
PASSWORD_ITERATIONS = 200_000


@dataclass(frozen=True)
class User:
    id: int
    email: str


@dataclass(frozen=True)
class CharacterSummary:
    id: int
    slot: int
    name: str
    ancestry: str
    location: str


class AuthStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or os.environ.get("NEON_KNIGHTS_DB", "neon_knights.sqlite3"))
        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_db(self) -> None:
        with self.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    ancestry TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    UNIQUE(user_id, slot),
                    UNIQUE(user_id, name COLLATE NOCASE)
                )
                """
            )

    def create_user(self, email: str, password: str) -> User:
        email = normalize_email(email)
        validate_password(password)
        salt, password_hash = hash_password(password)
        now = int(time.time())
        try:
            with self.connect() as db:
                cursor = db.execute(
                    """
                    INSERT INTO users (email, password_salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (email, salt, password_hash, now),
                )
                return User(id=int(cursor.lastrowid), email=email)
        except sqlite3.IntegrityError as exc:
            raise ValueError("That email is already signed up.") from exc

    def verify_user(self, email: str, password: str) -> User:
        email = normalize_email(email)
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or not verify_password(password, row["password_salt"], row["password_hash"]):
            raise ValueError("Email or password is incorrect.")
        return User(id=int(row["id"]), email=str(row["email"]))

    def get_user(self, user_id: int) -> User | None:
        with self.connect() as db:
            row = db.execute("SELECT id, email FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(id=int(row["id"]), email=str(row["email"])) if row else None

    def list_characters(self, user_id: int) -> list[CharacterSummary]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id, slot, name, ancestry, state_json
                FROM characters
                WHERE user_id = ?
                ORDER BY slot ASC
                """,
                (user_id,),
            ).fetchall()
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

        used_slots = {summary.slot for summary in summaries}
        slot = next(index for index in range(1, MAX_CHARACTERS_PER_ACCOUNT + 1) if index not in used_slots)
        character = Character(name=name, ancestry=ancestry)
        now = int(time.time())
        try:
            with self.connect() as db:
                cursor = db.execute(
                    """
                    INSERT INTO characters (user_id, slot, name, ancestry, state_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, slot, name, ancestry, character_to_json(character), now, now),
                )
                return int(cursor.lastrowid), character
        except sqlite3.IntegrityError as exc:
            raise ValueError("That character name is already used on this account.") from exc

    def load_character(self, user_id: int, character_id: int) -> Character:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM characters WHERE user_id = ? AND id = ?",
                (user_id, character_id),
            ).fetchone()
        if row is None:
            raise ValueError("Character not found.")
        return character_from_json(str(row["state_json"]))

    def save_character(self, user_id: int, character_id: int, character: Character) -> None:
        now = int(time.time())
        with self.connect() as db:
            db.execute(
                """
                UPDATE characters
                SET name = ?, ancestry = ?, state_json = ?, updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (
                    character.name,
                    character.ancestry,
                    character_to_json(character),
                    now,
                    user_id,
                    character_id,
                ),
            )


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    return email


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
