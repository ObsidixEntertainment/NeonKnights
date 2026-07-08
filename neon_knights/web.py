from __future__ import annotations

import argparse
import html
import json
import os
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .engine import GameSession
from .models import Character
from .world import ANCESTRIES, AUGMENTS, FACTIONS


SESSION_COOKIE = "nk_session"
SESSIONS: dict[str, GameSession] = {}


class NeonKnightsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class NeonKnightsHandler(BaseHTTPRequestHandler):
    server_version = "NeonKnightsWeb/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_html(render_index())
            return
        if path == "/healthz":
            self.send_text("ok")
            return
        if path == "/api/state":
            session = self.current_session()
            self.send_json({"hasSession": bool(session), "state": session_state(session) if session else None})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/new":
            try:
                session_id, output, state = start_session(
                    str(payload.get("name", "")),
                    str(payload.get("ancestry", "")),
                )
            except ValueError as exc:
                self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"output": output, "state": state}, cookie=session_id)
            return

        if path == "/api/command":
            session_id = self.current_session_id()
            if not session_id or session_id not in SESSIONS:
                self.send_json({"error": "Start a character first."}, status=HTTPStatus.CONFLICT)
                return
            output, state = run_command(session_id, str(payload.get("command", "")))
            self.send_json({"output": output, "state": state})
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

    def current_session_id(self) -> str | None:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie(cookie_header)
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def current_session(self) -> GameSession | None:
        session_id = self.current_session_id()
        if not session_id:
            return None
        return SESSIONS.get(session_id)

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
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={cookie}; Path=/; SameSite=Lax")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("NEON_KNIGHTS_QUIET") == "1":
            return
        super().log_message(fmt, *args)


def start_session(name: str, ancestry_key: str, sessions: dict[str, GameSession] = SESSIONS) -> tuple[str, str, dict[str, Any]]:
    name = " ".join(name.strip().split())
    ancestry_key = ancestry_key.strip().lower()

    if not name:
        raise ValueError("Handle is required.")
    if len(name) > 32:
        raise ValueError("Handle must be 32 characters or fewer.")
    if ancestry_key not in ANCESTRIES:
        raise ValueError("Choose a listed ancestry.")

    session_id = uuid4().hex
    session = GameSession(Character(name=name, ancestry=ancestry_key))
    sessions[session_id] = session
    return session_id, session.intro(), session_state(session)


def run_command(
    session_id: str,
    command: str,
    sessions: dict[str, GameSession] = SESSIONS,
) -> tuple[str, dict[str, Any] | None]:
    session = sessions[session_id]
    output = session.handle(command)
    if not session.running:
        sessions.pop(session_id, None)
        return output, None
    return output, session_state(session)


def session_state(session: GameSession) -> dict[str, Any]:
    character = session.character
    ancestry = ANCESTRIES[character.ancestry]
    faction = FACTIONS[character.faction].name if character.faction else "Unaffiliated"
    return {
        "name": character.name,
        "ancestry": ancestry.name,
        "faction": faction,
        "credits": character.credits,
        "essence": character.essence,
        "augments": [AUGMENTS[key].name for key in sorted(character.augments)],
        "location": session.room.name,
        "roomKey": session.room.key,
    }


def render_index() -> str:
    ancestry_options = "\n".join(
        f'<option value="{html.escape(key)}">{html.escape(ancestry.name)}</option>'
        for key, ancestry in ANCESTRIES.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Neon Knights MUD</title>
  <style>
    :root {{
      --ink: #f2f6ed;
      --muted: #9eaaa3;
      --line: rgba(242, 246, 237, 0.18);
      --red: #ff3f5f;
      --cyan: #18d9e6;
      --green: #7dff7a;
      --gold: #ffd166;
      --violet: #c47dff;
      --panel: rgba(10, 13, 15, 0.88);
      --paper: #121617;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 18%, rgba(255, 63, 95, 0.20), transparent 22rem),
        radial-gradient(circle at 82% 8%, rgba(24, 217, 230, 0.16), transparent 18rem),
        linear-gradient(160deg, #080909 0%, #15120f 44%, #071315 100%);
      font-family: Consolas, "Courier New", monospace;
    }}

    .chrome {{
      display: grid;
      grid-template-columns: minmax(15rem, 0.85fr) minmax(0, 2fr) minmax(15rem, 0.75fr);
      gap: 1rem;
      min-height: 100vh;
      padding: clamp(0.75rem, 2vw, 1.5rem);
    }}

    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1rem 3rem rgba(0, 0, 0, 0.32);
      overflow: hidden;
      min-height: 0;
    }}

    .mast {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1rem;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.035);
    }}

    h1, h2 {{
      margin: 0;
      line-height: 1.05;
      letter-spacing: 0;
    }}

    h1 {{
      font-size: clamp(1.35rem, 2rem, 2rem);
    }}

    h2 {{
      font-size: 0.9rem;
      color: var(--muted);
      text-transform: uppercase;
    }}

    .pulse {{
      width: 0.8rem;
      height: 0.8rem;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 1rem var(--green);
    }}

    .side {{
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 0;
    }}

    .map {{
      position: relative;
      min-height: 20rem;
      padding: 1rem;
      background:
        linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
        linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px);
      background-size: 2rem 2rem;
    }}

    .rail {{
      position: absolute;
      background: var(--line);
      transform-origin: left center;
      height: 2px;
    }}

    .r1 {{ left: 28%; top: 26%; width: 39%; transform: rotate(18deg); }}
    .r2 {{ left: 33%; top: 44%; width: 38%; transform: rotate(-12deg); }}
    .r3 {{ left: 30%; top: 62%; width: 42%; transform: rotate(16deg); }}
    .r4 {{ left: 49%; top: 25%; width: 2px; height: 45%; transform: none; }}

    .node {{
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
    }}

    .node.red {{ color: var(--red); }}
    .node.green {{ color: var(--green); }}
    .node.gold {{ color: var(--gold); }}
    .node.violet {{ color: var(--violet); }}
    .node.station {{ left: 42%; top: 40%; }}
    .node.blood {{ left: 15%; top: 20%; }}
    .node.pack {{ left: 18%; top: 64%; }}
    .node.hex {{ right: 14%; top: 18%; }}
    .node.synth {{ right: 16%; bottom: 20%; }}

    .terminal {{
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto auto;
      min-height: 0;
    }}

    .log {{
      min-height: 0;
      padding: 1rem;
      overflow: auto;
      white-space: pre-wrap;
      line-height: 1.45;
      background: rgba(0, 0, 0, 0.38);
    }}

    .line {{
      margin-bottom: 1rem;
    }}

    .line.input {{
      color: var(--cyan);
    }}

    .line.system {{
      color: var(--gold);
    }}

    .composer, .roll {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 0.5rem;
      padding: 0.85rem;
      border-top: 1px solid var(--line);
    }}

    input, select, button {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--ink);
      background: var(--paper);
      font: inherit;
    }}

    input, select {{
      width: 100%;
      padding: 0.78rem 0.85rem;
    }}

    button {{
      padding: 0.78rem 0.95rem;
      cursor: pointer;
      background: #1b2220;
    }}

    button:hover, button:focus-visible {{
      border-color: var(--cyan);
      color: white;
    }}

    .quick {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.45rem;
      padding: 0 0.85rem 0.85rem;
      border-top: 1px solid var(--line);
    }}

    .quick button {{
      padding: 0.6rem 0.4rem;
      color: var(--muted);
    }}

    .sheet {{
      padding: 1rem;
      display: grid;
      gap: 0.85rem;
    }}

    .stat {{
      display: grid;
      gap: 0.2rem;
      padding-bottom: 0.65rem;
      border-bottom: 1px solid var(--line);
    }}

    .label {{
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
    }}

    .value {{
      overflow-wrap: anywhere;
    }}

    .hidden {{
      display: none;
    }}

    @media (max-width: 980px) {{
      .chrome {{
        grid-template-columns: 1fr;
      }}

      .map {{
        min-height: 15rem;
      }}
    }}

    @media (min-width: 981px) {{
      .chrome {{
        height: 100vh;
        overflow: hidden;
      }}
    }}

    @media (max-width: 560px) {{
      .chrome {{
        padding: 0.5rem;
      }}

      .mast, .composer, .roll {{
        grid-template-columns: 1fr;
      }}

      .quick {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
  <main class="chrome">
    <section class="panel side" aria-label="City signal map">
      <div class="mast">
        <h2>Redline Grid</h2>
        <span class="pulse" aria-hidden="true"></span>
      </div>
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

      <form id="createForm" class="roll">
        <input id="handle" name="handle" maxlength="32" placeholder="Handle" autocomplete="off" required>
        <select id="ancestry" name="ancestry" aria-label="Ancestry">
          {ancestry_options}
        </select>
        <button type="submit">Enter</button>
      </form>

      <form id="commandForm" class="composer hidden">
        <input id="command" name="command" placeholder=">" autocomplete="off">
        <button type="submit">Send</button>
      </form>

      <div id="quickCommands" class="quick hidden">
        <button data-command="look">look</button>
        <button data-command="scan">scan</button>
        <button data-command="north">north</button>
        <button data-command="east">east</button>
        <button data-command="west">west</button>
        <button data-command="whoami">whoami</button>
      </div>
    </section>

    <aside class="panel" aria-label="Character sheet">
      <div class="mast">
        <h2>Body Ledger</h2>
      </div>
      <div class="sheet">
        <div class="stat"><span class="label">Handle</span><span id="sheetName" class="value">-</span></div>
        <div class="stat"><span class="label">Ancestry</span><span id="sheetAncestry" class="value">-</span></div>
        <div class="stat"><span class="label">Faction</span><span id="sheetFaction" class="value">-</span></div>
        <div class="stat"><span class="label">Credits</span><span id="sheetCredits" class="value">-</span></div>
        <div class="stat"><span class="label">Essence</span><span id="sheetEssence" class="value">-</span></div>
        <div class="stat"><span class="label">Augments</span><span id="sheetAugments" class="value">-</span></div>
      </div>
    </aside>
  </main>

  <script>
    const log = document.querySelector("#log");
    const createForm = document.querySelector("#createForm");
    const commandForm = document.querySelector("#commandForm");
    const commandInput = document.querySelector("#command");
    const quickCommands = document.querySelector("#quickCommands");

    const sheet = {{
      location: document.querySelector("#location"),
      name: document.querySelector("#sheetName"),
      ancestry: document.querySelector("#sheetAncestry"),
      faction: document.querySelector("#sheetFaction"),
      credits: document.querySelector("#sheetCredits"),
      essence: document.querySelector("#sheetEssence"),
      augments: document.querySelector("#sheetAugments")
    }};

    function append(text, kind = "") {{
      const line = document.createElement("div");
      line.className = `line ${{kind}}`;
      line.textContent = text;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
    }}

    function setActive(active) {{
      createForm.classList.toggle("hidden", active);
      commandForm.classList.toggle("hidden", !active);
      quickCommands.classList.toggle("hidden", !active);
      if (active) {{
        commandInput.focus();
      }}
    }}

    function renderState(state) {{
      if (!state) {{
        sheet.location.textContent = "No active body";
        sheet.name.textContent = "-";
        sheet.ancestry.textContent = "-";
        sheet.faction.textContent = "-";
        sheet.credits.textContent = "-";
        sheet.essence.textContent = "-";
        sheet.augments.textContent = "-";
        setActive(false);
        return;
      }}
      sheet.location.textContent = state.location;
      sheet.name.textContent = state.name;
      sheet.ancestry.textContent = state.ancestry;
      sheet.faction.textContent = state.faction;
      sheet.credits.textContent = state.credits;
      sheet.essence.textContent = state.essence;
      sheet.augments.textContent = state.augments.length ? state.augments.join(", ") : "None";
      setActive(true);
    }}

    async function postJson(url, payload) {{
      const response = await fetch(url, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || "Request failed.");
      }}
      return data;
    }}

    createForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      try {{
        const data = await postJson("/api/new", {{
          name: document.querySelector("#handle").value,
          ancestry: document.querySelector("#ancestry").value
        }});
        log.textContent = "";
        append(data.output, "system");
        renderState(data.state);
      }} catch (error) {{
        append(error.message, "system");
      }}
    }});

    commandForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const command = commandInput.value.trim();
      if (!command) return;
      commandInput.value = "";
      append(`> ${{command}}`, "input");
      try {{
        const data = await postJson("/api/command", {{ command }});
        append(data.output);
        renderState(data.state);
      }} catch (error) {{
        append(error.message, "system");
      }}
    }});

    quickCommands.addEventListener("click", (event) => {{
      const button = event.target.closest("button[data-command]");
      if (!button) return;
      commandInput.value = button.dataset.command;
      commandForm.requestSubmit();
    }});

    fetch("/api/state")
      .then((response) => response.json())
      .then((data) => {{
        renderState(data.state);
        if (data.hasSession) {{
          append("Session restored. Type look.", "system");
        }}
      }})
      .catch(() => append("Signal lost.", "system"));
  </script>
</body>
</html>"""


def serve(host: str, port: int) -> None:
    server = NeonKnightsHTTPServer((host, port), NeonKnightsHandler)
    print(f"Neon Knights browser MUD listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Neon Knights browser MUD.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
