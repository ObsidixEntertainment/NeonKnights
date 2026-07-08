from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .auth import AuthStore, CharacterSummary, MAX_CHARACTERS_PER_ACCOUNT
from .engine import GameSession
from .world import ANCESTRIES, AUGMENTS, FACTIONS, GEAR


AUTH_COOKIE = "nk_auth"
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
WEB_SESSIONS: dict[str, WebSession] = {}
_STORE: AuthStore | None = None


@dataclass
class WebSession:
    user_id: int
    email: str
    character_id: int | None = None
    game: GameSession | None = None


class NeonKnightsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class NeonKnightsHandler(BaseHTTPRequestHandler):
    server_version = "NeonKnightsWeb/0.2"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_html(render_index())
            return
        if path == "/healthz":
            self.send_text("ok")
            return
        if path == "/api/state":
            web_session = self.current_web_session()
            self.send_json(account_payload(web_session) if web_session else anonymous_payload())
            return
        if path.startswith("/static/"):
            self.send_static(path.removeprefix("/static/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/signup":
                token, response = signup(str(payload.get("email", "")), str(payload.get("password", "")))
                self.send_json(response, cookie=token)
                return

            if path == "/api/login":
                token, response = login(str(payload.get("email", "")), str(payload.get("password", "")))
                self.send_json(response, cookie=token)
                return

            if path == "/api/logout":
                token = self.current_token()
                if token:
                    WEB_SESSIONS.pop(token, None)
                self.send_json(anonymous_payload(), clear_cookie=True)
                return

            web_session = self.require_web_session()

            if path == "/api/character":
                output, response = create_character_for_session(
                    web_session,
                    str(payload.get("name", "")),
                    str(payload.get("ancestry", "")),
                )
                response["output"] = output
                self.send_json(response)
                return

            if path == "/api/select-character":
                output, response = select_character_for_session(web_session, int(payload.get("characterId", 0)))
                response["output"] = output
                self.send_json(response)
                return

            if path == "/api/command":
                output, response = run_command_for_session(web_session, str(payload.get("command", "")))
                response["output"] = output
                self.send_json(response)
                return

        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object.")
        return data

    def current_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie(cookie_header)
        morsel = cookie.get(AUTH_COOKIE)
        return morsel.value if morsel else None

    def current_web_session(self) -> WebSession | None:
        token = self.current_token()
        return WEB_SESSIONS.get(token) if token else None

    def require_web_session(self) -> WebSession:
        web_session = self.current_web_session()
        if web_session is None:
            raise ValueError("Log in or sign up first.")
        return web_session

    def send_static(self, relative_path: str) -> None:
        requested = (STATIC_ROOT / relative_path).resolve()
        if not str(requested).startswith(str(STATIC_ROOT.resolve())) or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        data = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        cookie: str | None = None,
        clear_cookie: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", f"{AUTH_COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Lax")
        if clear_cookie:
            self.send_header("Set-Cookie", f"{AUTH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("NEON_KNIGHTS_QUIET") == "1":
            return
        super().log_message(fmt, *args)


def get_store() -> AuthStore:
    global _STORE
    if _STORE is None:
        _STORE = AuthStore()
    return _STORE


def signup(email: str, password: str, store: AuthStore | None = None) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    user = store.create_user(email, password)
    token = uuid4().hex
    WEB_SESSIONS[token] = WebSession(user_id=user.id, email=user.email)
    return token, account_payload(WEB_SESSIONS[token], store)


def login(email: str, password: str, store: AuthStore | None = None) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    user = store.verify_user(email, password)
    token = uuid4().hex
    WEB_SESSIONS[token] = WebSession(user_id=user.id, email=user.email)
    return token, account_payload(WEB_SESSIONS[token], store)


def create_character_for_session(
    web_session: WebSession,
    name: str,
    ancestry: str,
    store: AuthStore | None = None,
) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    character_id, character = store.create_character(web_session.user_id, name, ancestry)
    game = GameSession(character)
    output = game.intro()
    web_session.character_id = character_id
    web_session.game = game
    store.save_character(web_session.user_id, character_id, game.character)
    return output, account_payload(web_session, store)


def select_character_for_session(
    web_session: WebSession,
    character_id: int,
    store: AuthStore | None = None,
) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    character = store.load_character(web_session.user_id, character_id)
    web_session.character_id = character_id
    web_session.game = GameSession(character)
    return f"Reconnected to {character.name}.\n\n{web_session.game.look()}", account_payload(web_session, store)


def run_command_for_session(
    web_session: WebSession,
    command: str,
    store: AuthStore | None = None,
) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    if web_session.game is None or web_session.character_id is None:
        raise ValueError("Select or create a character first.")

    output = web_session.game.handle(command)
    store.save_character(web_session.user_id, web_session.character_id, web_session.game.character)
    if not web_session.game.running:
        web_session.character_id = None
        web_session.game = None
    return output, account_payload(web_session, store)


def anonymous_payload() -> dict[str, Any]:
    return {
        "authenticated": False,
        "user": None,
        "characters": [],
        "maxCharacters": MAX_CHARACTERS_PER_ACCOUNT,
        "state": None,
    }


def account_payload(web_session: WebSession, store: AuthStore | None = None) -> dict[str, Any]:
    store = store or get_store()
    return {
        "authenticated": True,
        "user": {"email": web_session.email},
        "characters": [summary_to_dict(summary) for summary in store.list_characters(web_session.user_id)],
        "maxCharacters": MAX_CHARACTERS_PER_ACCOUNT,
        "currentCharacterId": web_session.character_id,
        "state": session_state(web_session.game, web_session.character_id) if web_session.game else None,
    }


def summary_to_dict(summary: CharacterSummary) -> dict[str, Any]:
    ancestry = ANCESTRIES.get(summary.ancestry)
    return {
        "id": summary.id,
        "slot": summary.slot,
        "name": summary.name,
        "ancestry": ancestry.name if ancestry else summary.ancestry,
        "location": summary.location,
    }


def session_state(session: GameSession | None, character_id: int | None = None) -> dict[str, Any] | None:
    if session is None:
        return None
    character = session.character
    ancestry = ANCESTRIES[character.ancestry]
    faction = FACTIONS[character.faction].name if character.faction else "Unaffiliated"
    return {
        "characterId": character_id,
        "name": character.name,
        "ancestry": ancestry.name,
        "faction": faction,
        "credits": character.credits,
        "essence": character.essence,
        "hp": character.hp,
        "maxHp": character.max_hp,
        "augments": [AUGMENTS[key].name for key in sorted(character.augments)],
        "inventory": [GEAR[key].name for key in sorted(character.inventory) if key in GEAR],
        "equipment": {
            slot: GEAR[key].name
            for slot, key in sorted(character.equipment.items())
            if key in GEAR
        },
        "location": session.room.name,
        "roomKey": session.room.key,
    }


def render_index() -> str:
    ancestry_options = "\n".join(
        f'<option value="{html.escape(key)}">{html.escape(ancestry.name)}</option>'
        for key, ancestry in ANCESTRIES.items()
    )
    return INDEX_HTML.replace("__ANCESTRY_OPTIONS__", ancestry_options)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Neon Knights</title>
  <style>
    :root {
      --ink: #f4f7ef;
      --muted: #a7b1ab;
      --line: rgba(244, 247, 239, 0.18);
      --red: #ff3f5f;
      --cyan: #19d7ef;
      --green: #7dff7a;
      --gold: #ffd166;
      --violet: #c47dff;
      --panel: rgba(8, 11, 13, 0.9);
      --paper: rgba(16, 22, 22, 0.96);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(3, 5, 8, 0.48), rgba(3, 5, 8, 0.88)),
        radial-gradient(circle at 12% 18%, rgba(255, 63, 95, 0.24), transparent 22rem),
        radial-gradient(circle at 82% 8%, rgba(24, 217, 230, 0.18), transparent 18rem),
        url("/static/images/neon-gothic-city.png") center / cover fixed no-repeat,
        #070b0d;
      font-family: Consolas, "Courier New", monospace;
    }

    .chrome {
      display: grid;
      grid-template-columns: minmax(16rem, 0.85fr) minmax(0, 2fr) minmax(16rem, 0.8fr);
      gap: 1rem;
      min-height: 100vh;
      padding: clamp(0.75rem, 2vw, 1.5rem);
      backdrop-filter: saturate(1.1);
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1rem 3rem rgba(0, 0, 0, 0.38);
      overflow: hidden;
      min-height: 0;
    }

    .mast {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1rem;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.04);
    }

    h1, h2 {
      margin: 0;
      line-height: 1.05;
      letter-spacing: 0;
    }

    h1 {
      font-size: 2rem;
    }

    h2 {
      font-size: 0.9rem;
      color: var(--muted);
      text-transform: uppercase;
    }

    .pulse {
      width: 0.8rem;
      height: 0.8rem;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 1rem var(--green);
    }

    .side {
      display: grid;
      grid-template-rows: auto auto 1fr;
      min-height: 0;
    }

    .map {
      position: relative;
      min-height: 17rem;
      padding: 1rem;
      background:
        linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
        linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px);
      background-size: 2rem 2rem;
    }

    .ascii {
      padding: 0.9rem 1rem;
      color: var(--cyan);
      white-space: pre;
      overflow: auto;
      border-bottom: 1px solid var(--line);
      background: rgba(0, 0, 0, 0.24);
      font-size: 0.78rem;
      line-height: 1.1;
    }

    .rail {
      position: absolute;
      background: var(--line);
      transform-origin: left center;
      height: 2px;
    }

    .r1 { left: 28%; top: 26%; width: 39%; transform: rotate(18deg); }
    .r2 { left: 33%; top: 44%; width: 38%; transform: rotate(-12deg); }
    .r3 { left: 30%; top: 62%; width: 42%; transform: rotate(16deg); }
    .r4 { left: 49%; top: 25%; width: 2px; height: 45%; transform: none; }

    .node {
      position: absolute;
      display: grid;
      place-items: center;
      width: 3.1rem;
      aspect-ratio: 1;
      border: 1px solid currentColor;
      border-radius: 50%;
      color: var(--cyan);
      background: rgba(0, 0, 0, 0.78);
      box-shadow: 0 0 1rem currentColor;
      font-weight: 700;
    }

    .node.red { color: var(--red); }
    .node.green { color: var(--green); }
    .node.gold { color: var(--gold); }
    .node.violet { color: var(--violet); }
    .node.station { left: 42%; top: 40%; }
    .node.blood { left: 15%; top: 20%; }
    .node.pack { left: 18%; top: 64%; }
    .node.hex { right: 14%; top: 18%; }
    .node.synth { right: 16%; bottom: 20%; }

    .terminal {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto auto auto;
      min-height: 0;
    }

    .log {
      min-height: 0;
      padding: 1rem;
      overflow: auto;
      white-space: pre-wrap;
      line-height: 1.45;
      background: rgba(0, 0, 0, 0.46);
    }

    .line {
      margin-bottom: 1rem;
    }

    .line.input {
      color: var(--cyan);
    }

    .line.system {
      color: var(--gold);
    }

    .auth-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      padding: 0.85rem;
      border-top: 1px solid var(--line);
    }

    .auth-form, .composer, .roll {
      display: grid;
      grid-template-columns: 1fr;
      gap: 0.5rem;
    }

    .composer, .roll {
      grid-template-columns: 1fr auto;
      padding: 0.85rem;
      border-top: 1px solid var(--line);
    }

    .roll {
      grid-template-columns: minmax(0, 1fr) minmax(8rem, 13rem) auto;
    }

    input, select, button {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--ink);
      background: var(--paper);
      font: inherit;
    }

    input, select {
      width: 100%;
      padding: 0.78rem 0.85rem;
    }

    button {
      padding: 0.78rem 0.95rem;
      cursor: pointer;
      background: rgba(27, 34, 32, 0.96);
    }

    button:hover, button:focus-visible {
      border-color: var(--cyan);
      color: white;
    }

    .quick {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0.45rem;
      padding: 0 0.85rem 0.85rem;
      border-top: 1px solid var(--line);
    }

    .quick button {
      padding: 0.6rem 0.35rem;
      color: var(--muted);
    }

    .sheet {
      padding: 1rem;
      display: grid;
      gap: 0.85rem;
      overflow: auto;
    }

    .stat {
      display: grid;
      gap: 0.2rem;
      padding-bottom: 0.65rem;
      border-bottom: 1px solid var(--line);
    }

    .label {
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
    }

    .value {
      overflow-wrap: anywhere;
    }

    .characters {
      display: grid;
      gap: 0.45rem;
    }

    .character-button {
      text-align: left;
      color: var(--ink);
    }

    .hidden {
      display: none;
    }

    @media (max-width: 980px) {
      .chrome {
        grid-template-columns: 1fr;
      }

      .map {
        min-height: 15rem;
      }
    }

    @media (min-width: 981px) {
      .chrome {
        height: 100vh;
        overflow: hidden;
      }
    }

    @media (max-width: 620px) {
      .chrome {
        padding: 0.5rem;
      }

      h1 {
        font-size: 1.65rem;
      }

      .auth-grid, .composer, .roll {
        grid-template-columns: 1fr;
      }

      .quick {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <main class="chrome">
    <section class="panel side" aria-label="City signal map">
      <div class="mast">
        <h2>Redline Grid</h2>
        <span class="pulse" aria-hidden="true"></span>
      </div>
      <pre class="ascii">       /\  NEON KNIGHTS  /\
  ____/  \____      ____/  \____
 |  red glass |____| chrome rain |
 |__cathedral_|    |__moon grid__|</pre>
      <div class="map" aria-hidden="true">
        <span class="rail r1"></span>
        <span class="rail r2"></span>
        <span class="rail r3"></span>
        <span class="rail r4"></span>
        <span class="node station">R</span>
        <span class="node red blood">B</span>
        <span class="node green pack">P</span>
        <span class="node violet hex">H</span>
        <span class="node gold synth">S</span>
      </div>
    </section>

    <section class="panel terminal" aria-label="Neon Knights terminal">
      <div class="mast">
        <div>
          <h1>Neon Knights</h1>
          <h2 id="location">No active body</h2>
        </div>
        <span class="pulse" aria-hidden="true"></span>
      </div>

      <div id="log" class="log" aria-live="polite"></div>

      <div id="authPanel" class="auth-grid">
        <form id="loginForm" class="auth-form">
          <input id="loginEmail" type="email" placeholder="Email" autocomplete="email" required>
          <input id="loginPassword" type="password" placeholder="Password" autocomplete="current-password" required>
          <button type="submit">Log In</button>
        </form>
        <form id="signupForm" class="auth-form">
          <input id="signupEmail" type="email" placeholder="Email" autocomplete="email" required>
          <input id="signupPassword" type="password" placeholder="Password" autocomplete="new-password" required>
          <button type="submit">Sign Up</button>
        </form>
      </div>

      <form id="createForm" class="roll hidden">
        <input id="handle" name="handle" maxlength="32" placeholder="Handle" autocomplete="off" required>
        <select id="ancestry" name="ancestry" aria-label="Ancestry">
          __ANCESTRY_OPTIONS__
        </select>
        <button type="submit">Create</button>
      </form>

      <form id="commandForm" class="composer hidden">
        <input id="command" name="command" placeholder=">" autocomplete="off">
        <button type="submit">Send</button>
      </form>

      <div id="quickCommands" class="quick hidden">
        <button data-command="look">look</button>
        <button data-command="scan">scan</button>
        <button data-command="shop">shop</button>
        <button data-command="inventory">inventory</button>
        <button data-command="gear">gear</button>
        <button data-command="north">north</button>
        <button data-command="attack">attack</button>
        <button data-command="tutorial">tutorial</button>
      </div>
    </section>

    <aside class="panel" aria-label="Character sheet">
      <div class="mast">
        <h2>Body Ledger</h2>
        <button id="logoutButton" class="hidden" type="button">Log Out</button>
      </div>
      <div class="sheet">
        <div class="stat"><span class="label">Email</span><span id="sheetEmail" class="value">-</span></div>
        <div class="stat"><span class="label">Slots</span><span id="sheetSlots" class="value">0/2</span></div>
        <div id="characterList" class="characters hidden"></div>
        <div class="stat"><span class="label">Handle</span><span id="sheetName" class="value">-</span></div>
        <div class="stat"><span class="label">Ancestry</span><span id="sheetAncestry" class="value">-</span></div>
        <div class="stat"><span class="label">Faction</span><span id="sheetFaction" class="value">-</span></div>
        <div class="stat"><span class="label">Health</span><span id="sheetHealth" class="value">-</span></div>
        <div class="stat"><span class="label">Credits</span><span id="sheetCredits" class="value">-</span></div>
        <div class="stat"><span class="label">Essence</span><span id="sheetEssence" class="value">-</span></div>
        <div class="stat"><span class="label">Gear</span><span id="sheetGear" class="value">-</span></div>
        <div class="stat"><span class="label">Inventory</span><span id="sheetInventory" class="value">-</span></div>
        <div class="stat"><span class="label">Augments</span><span id="sheetAugments" class="value">-</span></div>
      </div>
    </aside>
  </main>

  <script>
    const log = document.querySelector("#log");
    const authPanel = document.querySelector("#authPanel");
    const loginForm = document.querySelector("#loginForm");
    const signupForm = document.querySelector("#signupForm");
    const createForm = document.querySelector("#createForm");
    const commandForm = document.querySelector("#commandForm");
    const commandInput = document.querySelector("#command");
    const quickCommands = document.querySelector("#quickCommands");
    const characterList = document.querySelector("#characterList");
    const logoutButton = document.querySelector("#logoutButton");

    const sheet = {
      location: document.querySelector("#location"),
      email: document.querySelector("#sheetEmail"),
      slots: document.querySelector("#sheetSlots"),
      name: document.querySelector("#sheetName"),
      ancestry: document.querySelector("#sheetAncestry"),
      faction: document.querySelector("#sheetFaction"),
      health: document.querySelector("#sheetHealth"),
      credits: document.querySelector("#sheetCredits"),
      essence: document.querySelector("#sheetEssence"),
      gear: document.querySelector("#sheetGear"),
      inventory: document.querySelector("#sheetInventory"),
      augments: document.querySelector("#sheetAugments")
    };

    function append(text, kind = "") {
      const line = document.createElement("div");
      line.className = `line ${kind}`;
      line.textContent = text;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
    }

    function setMode(account) {
      const authed = Boolean(account?.authenticated);
      const active = Boolean(account?.state);
      const slotsUsed = account?.characters?.length || 0;
      const maxSlots = account?.maxCharacters || 2;

      authPanel.classList.toggle("hidden", authed);
      logoutButton.classList.toggle("hidden", !authed);
      createForm.classList.toggle("hidden", !authed || active || slotsUsed >= maxSlots);
      commandForm.classList.toggle("hidden", !active);
      quickCommands.classList.toggle("hidden", !active);
      characterList.classList.toggle("hidden", !authed || active || slotsUsed === 0);

      if (active) {
        commandInput.focus();
      }
    }

    function renderCharacters(account) {
      characterList.textContent = "";
      if (!account?.characters?.length || account.state) return;

      for (const character of account.characters) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "character-button";
        button.dataset.characterId = character.id;
        button.textContent = `${character.slot}. ${character.name} / ${character.ancestry} / ${character.location}`;
        characterList.appendChild(button);
      }
    }

    function renderAccount(account) {
      sheet.email.textContent = account?.user?.email || "-";
      sheet.slots.textContent = `${account?.characters?.length || 0}/${account?.maxCharacters || 2}`;
      renderCharacters(account);
      renderState(account?.state || null);
      setMode(account);
    }

    function renderState(state) {
      if (!state) {
        sheet.location.textContent = "No active body";
        sheet.name.textContent = "-";
        sheet.ancestry.textContent = "-";
        sheet.faction.textContent = "-";
        sheet.health.textContent = "-";
        sheet.credits.textContent = "-";
        sheet.essence.textContent = "-";
        sheet.gear.textContent = "-";
        sheet.inventory.textContent = "-";
        sheet.augments.textContent = "-";
        return;
      }
      sheet.location.textContent = state.location;
      sheet.name.textContent = state.name;
      sheet.ancestry.textContent = state.ancestry;
      sheet.faction.textContent = state.faction;
      sheet.health.textContent = `${state.hp}/${state.maxHp}`;
      sheet.credits.textContent = state.credits;
      sheet.essence.textContent = state.essence;
      sheet.gear.textContent = Object.entries(state.equipment).map(([slot, item]) => `${slot}: ${item}`).join(", ") || "None";
      sheet.inventory.textContent = state.inventory.length ? state.inventory.join(", ") : "None";
      sheet.augments.textContent = state.augments.length ? state.augments.join(", ") : "None";
    }

    async function postJson(url, payload = {}) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/login", {
          email: document.querySelector("#loginEmail").value,
          password: document.querySelector("#loginPassword").value
        });
        log.textContent = "";
        append("Account linked. Select a body or create one.", "system");
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    signupForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/signup", {
          email: document.querySelector("#signupEmail").value,
          password: document.querySelector("#signupPassword").value
        });
        log.textContent = "";
        append("Account created. Two character slots are available.", "system");
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/character", {
          name: document.querySelector("#handle").value,
          ancestry: document.querySelector("#ancestry").value
        });
        log.textContent = "";
        append(data.output, "system");
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    characterList.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-character-id]");
      if (!button) return;
      try {
        const data = await postJson("/api/select-character", {
          characterId: Number(button.dataset.characterId)
        });
        log.textContent = "";
        append(data.output, "system");
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    commandForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const command = commandInput.value.trim();
      if (!command) return;
      commandInput.value = "";
      append(`> ${command}`, "input");
      try {
        const data = await postJson("/api/command", { command });
        append(data.output);
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    quickCommands.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-command]");
      if (!button) return;
      commandInput.value = button.dataset.command;
      commandForm.requestSubmit();
    });

    logoutButton.addEventListener("click", async () => {
      const data = await postJson("/api/logout");
      log.textContent = "";
      append("Logged out.", "system");
      renderAccount(data);
    });

    fetch("/api/state")
      .then((response) => response.json())
      .then((data) => {
        renderAccount(data);
        if (data.authenticated && data.state) {
          append("Session restored. Type look.", "system");
        } else if (data.authenticated) {
          append("Account restored. Select a body or create one.", "system");
        }
      })
      .catch(() => append("Signal lost.", "system"));
  </script>
</body>
</html>"""


def serve(host: str, port: int) -> None:
    server = NeonKnightsHTTPServer((host, port), NeonKnightsHandler)
    print(f"Neon Knights browser RPG listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neon Knights browser MUD.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
