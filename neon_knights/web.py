from __future__ import annotations

import argparse
import hmac
import html
import json
import mimetypes
import os
import time
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .auth import AuthStore, CharacterSummary, MAX_CHARACTERS_PER_ACCOUNT, User
from .engine import GameSession
from .mailer import MailResult, send_mail
from .world import ANCESTRIES, AUGMENTS, FACTIONS, GEAR


AUTH_COOKIE = "nk_auth"
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
INDEX_TEMPLATE_PATH = STATIC_ROOT / "index.html"
WEB_SESSIONS: dict[str, WebSession] = {}
_STORE: AuthStore | None = None


@dataclass
class WebSession:
    user_id: int
    email: str
    email_verified: bool = False
    is_admin: bool = False
    character_id: int | None = None
    game: GameSession | None = None


@dataclass(frozen=True)
class AdminCommandResult:
    output: str
    clear_sessions: bool = False


class NeonKnightsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class NeonKnightsHandler(BaseHTTPRequestHandler):
    server_version = "NeonKnightsWeb/0.6"

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

            if path == "/api/admin/bootstrap":
                token, response = admin_bootstrap(
                    str(payload.get("email", "")),
                    str(payload.get("password", "")),
                    str(payload.get("bootstrapKey", "")),
                )
                self.send_json(response, cookie=token)
                return

            if path == "/api/admin/reset-users":
                response = admin_reset_users(str(payload.get("bootstrapKey", "")))
                self.send_json(response, clear_cookie=True)
                return

            if path == "/api/request-password-reset":
                response = request_password_reset(str(payload.get("email", "")))
                self.send_json(response)
                return

            if path == "/api/reset-password":
                response = reset_password(
                    str(payload.get("email", "")),
                    str(payload.get("code", "")),
                    str(payload.get("password", "")),
                )
                self.send_json(response)
                return

            if path == "/api/logout":
                token = self.current_token()
                if token:
                    WEB_SESSIONS.pop(token, None)
                self.send_json(anonymous_payload(), clear_cookie=True)
                return

            web_session = self.require_web_session()

            if path == "/api/request-email-code":
                response = request_email_code_for_session(web_session)
                self.send_json(response)
                return

            if path == "/api/verify-email":
                response = verify_email_for_session(web_session, str(payload.get("code", "")))
                self.send_json(response)
                return

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
    WEB_SESSIONS[token] = web_session_from_user(user)
    delivery = send_account_email(user, store, "signup")
    return token, with_mail(account_payload(WEB_SESSIONS[token], store), delivery)


def login(email: str, password: str, store: AuthStore | None = None) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    user = store.verify_user(email, password)
    token = uuid4().hex
    WEB_SESSIONS[token] = web_session_from_user(user)
    delivery = send_account_email(user, store, "login")
    return token, with_mail(account_payload(WEB_SESSIONS[token], store), delivery)


def admin_bootstrap(
    email: str,
    password: str,
    bootstrap_key: str,
    store: AuthStore | None = None,
) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    expected = os.environ.get("NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY", "")
    if not expected:
        raise ValueError("Admin bootstrap key is not configured on this server.")
    if store.admin_count() > 0:
        raise ValueError("Admin bootstrap is closed because an admin already exists.")
    if not hmac.compare_digest(bootstrap_key.strip(), expected.strip()):
        raise ValueError("Admin bootstrap key is incorrect.")

    existing = store.get_user_by_email(email)
    if existing:
        user = store.verify_user(email, password)
        user = store.promote_admin(user.id)
    else:
        user = store.create_user(email, password, is_admin=True)

    token = uuid4().hex
    WEB_SESSIONS[token] = web_session_from_user(user)
    delivery = send_account_email(user, store, "admin-bootstrap")
    response = with_mail(account_payload(WEB_SESSIONS[token], store), delivery)
    response["output"] = "First admin account claimed. Your admin login details were sent to your email channel."
    return token, response


def admin_reset_users(bootstrap_key: str, store: AuthStore | None = None) -> dict[str, Any]:
    store = store or get_store()
    expected = os.environ.get("NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY", "")
    if not expected:
        raise ValueError("Admin bootstrap key is not configured on this server.")
    if not hmac.compare_digest(bootstrap_key.strip(), expected.strip()):
        raise ValueError("Admin bootstrap key is incorrect.")

    summary = store.reset_all_accounts()
    WEB_SESSIONS.clear()
    response = anonymous_payload()
    response["output"] = reset_summary_output(summary)
    return response


def request_password_reset(email: str, store: AuthStore | None = None) -> dict[str, Any]:
    store = store or get_store()
    user = store.get_user_by_email(email)
    delivery: MailResult | None = None
    if user is not None:
        code = store.create_email_code(user.id, "password-reset")
        delivery = safe_send_mail(user.email, "Neon Knights password reset", password_reset_body(user, code))
    response = anonymous_payload()
    response["output"] = "If that email exists, a reset code was sent."
    if delivery is not None:
        response["emailDelivery"] = mail_result_to_dict(delivery)
    return response


def reset_password(email: str, code: str, password: str, store: AuthStore | None = None) -> dict[str, Any]:
    store = store or get_store()
    user = store.get_user_by_email(email)
    if user is None:
        raise ValueError("Password reset failed.")
    store.verify_email_code(user.id, code, "password-reset")
    user = store.set_password(user.id, password)
    delivery = safe_send_mail(user.email, "Neon Knights password changed", password_changed_body(user))
    response = with_mail(anonymous_payload(), delivery)
    response["output"] = "Password updated. Log in with the new password."
    return response


def web_session_from_user(user: User) -> WebSession:
    return WebSession(
        user_id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        is_admin=user.is_admin,
    )


def refresh_web_session_user(web_session: WebSession, store: AuthStore) -> User:
    user = store.get_user(web_session.user_id)
    if user is None:
        raise ValueError("Account not found.")
    web_session.email = user.email
    web_session.email_verified = user.email_verified
    web_session.is_admin = user.is_admin
    return user


def request_email_code_for_session(web_session: WebSession, store: AuthStore | None = None) -> dict[str, Any]:
    store = store or get_store()
    user = refresh_web_session_user(web_session, store)
    delivery = send_account_email(user, store, "verify-email")
    response = with_mail(account_payload(web_session, store), delivery)
    response["output"] = "Email verification code sent."
    return response


def verify_email_for_session(
    web_session: WebSession,
    code: str,
    store: AuthStore | None = None,
) -> dict[str, Any]:
    store = store or get_store()
    user = store.verify_email_code(web_session.user_id, code)
    web_session.email_verified = user.email_verified
    web_session.is_admin = user.is_admin
    response = account_payload(web_session, store)
    response["output"] = "Email verified."
    return response


def create_character_for_session(
    web_session: WebSession,
    name: str,
    ancestry: str,
    store: AuthStore | None = None,
) -> tuple[str, dict[str, Any]]:
    store = store or get_store()
    enforce_verified_email(web_session, store)
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
    enforce_verified_email(web_session, store)
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
    admin_result = maybe_handle_admin_command(web_session, command, store)
    if admin_result is not None:
        if admin_result.clear_sessions:
            WEB_SESSIONS.clear()
            return admin_result.output, anonymous_payload()
        return admin_result.output, account_payload(web_session, store)

    if web_session.game is None or web_session.character_id is None:
        raise ValueError("Select or create a character first.")

    enforce_verified_email(web_session, store)

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
    user = refresh_web_session_user(web_session, store)
    return {
        "authenticated": True,
        "user": {
            "email": user.email,
            "emailVerified": user.email_verified,
            "isAdmin": user.is_admin,
        },
        "characters": [summary_to_dict(summary) for summary in store.list_characters(web_session.user_id)],
        "maxCharacters": MAX_CHARACTERS_PER_ACCOUNT,
        "currentCharacterId": web_session.character_id,
        "state": session_state(web_session.game, web_session.character_id) if web_session.game else None,
    }


def enforce_verified_email(web_session: WebSession, store: AuthStore) -> None:
    if os.environ.get("NEON_KNIGHTS_REQUIRE_EMAIL_VERIFICATION", "0") != "1":
        return
    user = refresh_web_session_user(web_session, store)
    if not user.email_verified:
        raise ValueError("Verify your email before entering the city.")


def maybe_handle_admin_command(web_session: WebSession, command: str, store: AuthStore) -> AdminCommandResult | None:
    command = " ".join(command.strip().split())
    if not command.lower().startswith("admin"):
        return None

    user = refresh_web_session_user(web_session, store)
    if not user.is_admin:
        return AdminCommandResult("Admin channel denied.")

    _, _, rest = command.partition(" ")
    verb, _, target = rest.strip().partition(" ")
    verb = verb.lower()
    target = target.strip()

    if not verb or verb == "help":
        return AdminCommandResult(
            "\n".join(
                [
                    "Admin commands:",
                    "  admin users                List accounts and roles.",
                    "  admin codes [email]        Show recent verification/reset codes.",
                    "  admin grant <email>        Promote an existing account to admin.",
                    "  admin verify <email>       Mark an account email as verified.",
                    "  admin reset-users CONFIRM  Reset all users, characters, and codes.",
                    "  admin me                   Show your admin account.",
                ]
            )
        )
    if verb == "me":
        return AdminCommandResult(f"Admin: {user.email} | verified={user.email_verified}")
    if verb == "users":
        lines = ["Accounts:"]
        for listed in store.list_users():
            role = "admin" if listed.is_admin else "user"
            verified = "verified" if listed.email_verified else "unverified"
            character_count = len(store.list_characters(listed.id))
            lines.append(f"- {listed.email} | {role} | {verified} | characters={character_count}")
        return AdminCommandResult("\n".join(lines))
    if verb in {"codes", "mail"}:
        return AdminCommandResult(admin_codes(store, target or None))
    if verb == "grant":
        if not target:
            return AdminCommandResult("Usage: admin grant <email>")
        target_user = store.get_user_by_email(target)
        if target_user is None:
            return AdminCommandResult(f"No account exists for {target}.")
        promoted = store.promote_admin(target_user.id)
        delivery = safe_send_mail(
            promoted.email,
            "Neon Knights admin access granted",
            admin_grant_body(promoted),
        )
        return AdminCommandResult(f"Granted admin to {promoted.email}. {delivery.detail}")
    if verb == "verify":
        if not target:
            return AdminCommandResult("Usage: admin verify <email>")
        target_user = store.get_user_by_email(target)
        if target_user is None:
            return AdminCommandResult(f"No account exists for {target}.")
        verified = store.set_email_verified(target_user.id)
        return AdminCommandResult(f"Verified email for {verified.email}.")
    if verb == "reset-users":
        if target.upper() != "CONFIRM":
            return AdminCommandResult("Usage: admin reset-users CONFIRM")
        summary = store.reset_all_accounts()
        return AdminCommandResult(reset_summary_output(summary), clear_sessions=True)
    return AdminCommandResult(f"Unknown admin command: {verb}. Try 'admin help'.")


def reset_summary_output(summary: Any) -> str:
    return (
        "All users, characters, and email codes were reset. "
        "Bootstrap is open again. "
        f"Removed users={summary.users}, characters={summary.characters}, email_codes={summary.email_codes}."
    )


def admin_codes(store: AuthStore, email: str | None = None) -> str:
    try:
        codes = store.list_email_codes(email=email, limit=10)
    except ValueError as exc:
        return str(exc)
    if not codes:
        suffix = f" for {email}" if email else ""
        return f"No email codes found{suffix}."

    now = int(time.time())
    lines = ["Recent email codes:"]
    for code in codes:
        if code.used_at is not None:
            status = "used"
        elif code.expires_at < now:
            status = "expired"
        else:
            status = "active"
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(code.created_at))
        expires = time.strftime("%H:%M:%S", time.localtime(code.expires_at))
        lines.append(
            f"- {code.email} | {code.purpose} | {code.code} | {status} | created {created} | expires {expires}"
        )
    return "\n".join(lines)


def send_account_email(user: User, store: AuthStore, event: str) -> MailResult:
    code = store.create_email_code(user.id)
    if event == "admin-bootstrap":
        subject = "Neon Knights first admin login"
        body = admin_bootstrap_body(user, code)
    elif event == "login":
        subject = "Neon Knights login notice"
        body = login_notice_body(user, code)
    else:
        subject = "Neon Knights email verification"
        body = verification_body(user, code)
    result = safe_send_mail(user.email, subject, body)
    if should_pass_through_code(result, event):
        return replace(result, code=code, purpose="verify-email")
    return replace(result, purpose="verify-email")


def should_pass_through_code(result: MailResult, event: str) -> bool:
    if result.sent:
        return False
    if os.environ.get("NEON_KNIGHTS_PASS_THROUGH_CODES", "1") == "0":
        return False
    return event in {"signup", "login", "verify-email", "admin-bootstrap"}


def safe_send_mail(recipient: str, subject: str, body: str) -> MailResult:
    try:
        return send_mail(recipient, subject, body)
    except Exception as exc:
        return MailResult(recipient, subject, False, f"Email delivery failed: {exc}")


def with_mail(payload: dict[str, Any], result: MailResult) -> dict[str, Any]:
    payload["emailDelivery"] = mail_result_to_dict(result)
    return payload


def mail_result_to_dict(result: MailResult) -> dict[str, Any]:
    payload = {
        "recipient": result.recipient,
        "subject": result.subject,
        "sent": result.sent,
        "detail": result.detail,
    }
    if result.code:
        payload["code"] = result.code
        payload["purpose"] = result.purpose or "verify-email"
    return payload


def verification_body(user: User, code: str) -> str:
    role = "Admin" if user.is_admin else "Player"
    return (
        "Welcome to Neon Knights.\n\n"
        f"Account: {user.email}\n"
        f"Role: {role}\n"
        f"Email verification code: {code}\n\n"
        "Enter this code in the browser to mark your account email as verified. "
        "Your password is never emailed or stored in plain text.\n"
    )


def login_notice_body(user: User, code: str) -> str:
    role = "Admin" if user.is_admin else "Player"
    verified = "yes" if user.email_verified else "no"
    return (
        "Neon Knights login notice.\n\n"
        f"Account: {user.email}\n"
        f"Role: {role}\n"
        f"Email verified: {verified}\n"
        f"Fresh verification code: {code}\n\n"
        "If this was not you, change your password as soon as reset support is enabled. "
        "Neon Knights never emails your password.\n"
    )


def password_reset_body(user: User, code: str) -> str:
    role = "Admin" if user.is_admin else "Player"
    return (
        "Neon Knights password reset requested.\n\n"
        f"Account: {user.email}\n"
        f"Role: {role}\n"
        f"Password reset code: {code}\n\n"
        "Enter this code in the browser with a new password. If you did not request this, ignore this email.\n"
    )


def password_changed_body(user: User) -> str:
    role = "Admin" if user.is_admin else "Player"
    return (
        "Your Neon Knights password was changed.\n\n"
        f"Account: {user.email}\n"
        f"Role: {role}\n\n"
        "If this was not you, contact an admin immediately. Neon Knights never emails your password.\n"
    )


def admin_bootstrap_body(user: User, code: str) -> str:
    return (
        "Your first Neon Knights admin account was claimed.\n\n"
        f"Admin login email: {user.email}\n"
        "Admin login password: the password you just entered in the browser.\n"
        f"Email verification code: {code}\n\n"
        "Keep the bootstrap key private. Once the first admin exists, bootstrap closes automatically.\n"
    )


def admin_grant_body(user: User) -> str:
    return (
        "Neon Knights admin access was granted to this account.\n\n"
        f"Admin login email: {user.email}\n"
        "Log in with your existing password. Neon Knights never emails your password.\n"
    )


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
    template = INDEX_TEMPLATE_PATH.read_text(encoding="utf-8") if INDEX_TEMPLATE_PATH.exists() else INDEX_HTML
    return template.replace("__ANCESTRY_OPTIONS__", ancestry_options)


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
      grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
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

    .verify {
      grid-template-columns: 1fr auto auto;
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

      .verify {
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
        <form id="adminForm" class="auth-form">
          <input id="adminEmail" type="email" placeholder="Admin email" autocomplete="email" required>
          <input id="adminPassword" type="password" placeholder="Admin password" autocomplete="new-password" required>
          <input id="adminBootstrapKey" type="password" placeholder="Bootstrap key" autocomplete="one-time-code" required>
          <button type="submit">Claim Admin</button>
        </form>
        <form id="resetForm" class="auth-form">
          <input id="resetEmail" type="email" placeholder="Reset email" autocomplete="email" required>
          <input id="resetCode" maxlength="12" placeholder="Reset code" autocomplete="one-time-code">
          <input id="resetPassword" type="password" placeholder="New password" autocomplete="new-password">
          <button id="sendResetButton" type="button">Send Reset</button>
          <button type="submit">Set Password</button>
        </form>
      </div>

      <form id="verifyForm" class="composer verify hidden">
        <input id="emailCode" name="emailCode" maxlength="12" placeholder="Email code" autocomplete="one-time-code">
        <button type="submit">Verify</button>
        <button id="sendCodeButton" type="button">Send Code</button>
      </form>

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
        <div class="stat"><span class="label">Role</span><span id="sheetRole" class="value">-</span></div>
        <div class="stat"><span class="label">Email Auth</span><span id="sheetEmailAuth" class="value">-</span></div>
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
    const adminForm = document.querySelector("#adminForm");
    const resetForm = document.querySelector("#resetForm");
    const sendResetButton = document.querySelector("#sendResetButton");
    const verifyForm = document.querySelector("#verifyForm");
    const sendCodeButton = document.querySelector("#sendCodeButton");
    const createForm = document.querySelector("#createForm");
    const commandForm = document.querySelector("#commandForm");
    const commandInput = document.querySelector("#command");
    const quickCommands = document.querySelector("#quickCommands");
    const characterList = document.querySelector("#characterList");
    const logoutButton = document.querySelector("#logoutButton");

    const sheet = {
      location: document.querySelector("#location"),
      email: document.querySelector("#sheetEmail"),
      role: document.querySelector("#sheetRole"),
      emailAuth: document.querySelector("#sheetEmailAuth"),
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
      const admin = Boolean(account?.user?.isAdmin);
      const emailVerified = Boolean(account?.user?.emailVerified);
      const slotsUsed = account?.characters?.length || 0;
      const maxSlots = account?.maxCharacters || 2;
      const commandReady = active || (authed && admin);

      authPanel.classList.toggle("hidden", authed);
      logoutButton.classList.toggle("hidden", !authed);
      verifyForm.classList.toggle("hidden", !authed || emailVerified);
      createForm.classList.toggle("hidden", !authed || active || slotsUsed >= maxSlots);
      commandForm.classList.toggle("hidden", !commandReady);
      quickCommands.classList.toggle("hidden", !active);
      characterList.classList.toggle("hidden", !authed || active || slotsUsed === 0);

      if (commandReady) {
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
      sheet.role.textContent = account?.user?.isAdmin ? "Admin" : (account?.authenticated ? "Player" : "-");
      sheet.emailAuth.textContent = account?.user?.emailVerified ? "Verified" : (account?.authenticated ? "Unverified" : "-");
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

    function appendDelivery(data) {
      if (data?.emailDelivery?.detail) {
        append(data.emailDelivery.detail, "system");
      }
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
        appendDelivery(data);
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
        appendDelivery(data);
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    adminForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/admin/bootstrap", {
          email: document.querySelector("#adminEmail").value,
          password: document.querySelector("#adminPassword").value,
          bootstrapKey: document.querySelector("#adminBootstrapKey").value
        });
        log.textContent = "";
        append(data.output || "Admin account claimed.", "system");
        appendDelivery(data);
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    sendResetButton.addEventListener("click", async () => {
      try {
        const data = await postJson("/api/request-password-reset", {
          email: document.querySelector("#resetEmail").value
        });
        append(data.output || "Reset code sent.", "system");
        appendDelivery(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    resetForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/reset-password", {
          email: document.querySelector("#resetEmail").value,
          code: document.querySelector("#resetCode").value,
          password: document.querySelector("#resetPassword").value
        });
        append(data.output || "Password updated.", "system");
        appendDelivery(data);
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    verifyForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = await postJson("/api/verify-email", {
          code: document.querySelector("#emailCode").value
        });
        append(data.output || "Email verified.", "system");
        renderAccount(data);
      } catch (error) {
        append(error.message, "system");
      }
    });

    sendCodeButton.addEventListener("click", async () => {
      try {
        const data = await postJson("/api/request-email-code");
        append(data.output || "Email code sent.", "system");
        appendDelivery(data);
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
    parser = argparse.ArgumentParser(description="Run the Neon Knights browser RPG.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
