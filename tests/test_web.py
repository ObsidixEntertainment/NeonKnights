from __future__ import annotations

import os
import tempfile
import unittest

from neon_knights.auth import AuthStore
from neon_knights.web import (
    WEB_SESSIONS,
    admin_bootstrap,
    create_character_for_session,
    login,
    request_email_code_for_session,
    run_command_for_session,
    select_character_for_session,
    signup,
)


def restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


class WebSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        WEB_SESSIONS.clear()
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AuthStore(f"{self.tempdir.name}/test.sqlite3")
        self.old_outbox = os.environ.get("NEON_KNIGHTS_MAIL_OUTBOX")
        self.old_admin_key = os.environ.get("NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY")
        os.environ["NEON_KNIGHTS_MAIL_OUTBOX"] = f"{self.tempdir.name}/outbox"
        os.environ["NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY"] = "test-admin-key"

    def tearDown(self) -> None:
        WEB_SESSIONS.clear()
        restore_env("NEON_KNIGHTS_MAIL_OUTBOX", self.old_outbox)
        restore_env("NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY", self.old_admin_key)
        self.tempdir.cleanup()

    def test_signup_character_creation_and_demon_state(self) -> None:
        token, signup_account = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]

        output, account = create_character_for_session(web_session, "Runner", "demon", self.store)

        self.assertTrue(account["authenticated"])
        self.assertIn("Welcome to Neon Knights", output)
        self.assertEqual(account["user"]["email"], "runner@example.com")
        self.assertEqual(account["state"]["name"], "Runner")
        self.assertEqual(account["state"]["ancestry"], "Demon")
        self.assertEqual(account["state"]["location"], "Redline Station")
        self.assertEqual(account["maxCharacters"], 2)
        self.assertFalse(account["user"]["emailVerified"])
        self.assertFalse(account["user"]["isAdmin"])
        self.assertIn("emailDelivery", signup_account)

    def test_login_and_command_updates_persisted_state(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]
        create_character_for_session(web_session, "Runner", "witch", self.store)

        output, account = run_command_for_session(web_session, "north", self.store)

        self.assertIn("Neon Bazaar", output)
        self.assertEqual(account["state"]["location"], "Neon Bazaar")

        login_token, login_account = login("runner@example.com", "neonpass", self.store)
        logged_in_session = WEB_SESSIONS[login_token]
        character_id = login_account["characters"][0]["id"]
        output, login_account = select_character_for_session(logged_in_session, character_id, self.store)

        self.assertIn("Reconnected to Runner", output)
        self.assertEqual(login_account["state"]["location"], "Neon Bazaar")

    def test_two_character_limit_per_email(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]
        create_character_for_session(web_session, "One", "witch", self.store)
        run_command_for_session(web_session, "quit", self.store)
        create_character_for_session(web_session, "Two", "demon", self.store)
        run_command_for_session(web_session, "quit", self.store)

        with self.assertRaisesRegex(ValueError, "two characters"):
            create_character_for_session(web_session, "Three", "cyborg", self.store)

    def test_shop_buy_equip_and_inventory_commands(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]
        create_character_for_session(web_session, "Runner", "witch", self.store)
        run_command_for_session(web_session, "north", self.store)

        shop, _ = run_command_for_session(web_session, "shop", self.store)
        buy, account = run_command_for_session(web_session, "buy neon-dagger", self.store)
        equip, account = run_command_for_session(web_session, "equip neon-dagger", self.store)
        inventory, _ = run_command_for_session(web_session, "inventory", self.store)

        self.assertIn("Neon Dagger", shop)
        self.assertIn("Bought Neon Dagger", buy)
        self.assertIn("Equipped Neon Dagger", equip)
        self.assertEqual(account["state"]["equipment"]["weapon"], "Neon Dagger")
        self.assertIn("Neon Dagger", inventory)

    def test_quit_clears_active_character_but_keeps_account_session(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]
        create_character_for_session(web_session, "Runner", "witch", self.store)

        output, account = run_command_for_session(web_session, "quit", self.store)

        self.assertIn("disconnect", output)
        self.assertIsNone(account["state"])
        self.assertIn(token, WEB_SESSIONS)

    def test_request_email_code_uses_mail_outbox(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]

        account = request_email_code_for_session(web_session, self.store)

        self.assertIn("emailDelivery", account)
        self.assertFalse(account["emailDelivery"]["sent"])
        self.assertIn("outbox", account["emailDelivery"]["detail"])

    def test_admin_bootstrap_and_admin_command(self) -> None:
        token, bootstrap_account = admin_bootstrap("admin@example.com", "neonpass", "test-admin-key", self.store)
        web_session = WEB_SESSIONS[token]

        output, account = run_command_for_session(web_session, "admin users", self.store)

        self.assertTrue(account["user"]["isAdmin"])
        self.assertIn("First admin account claimed", bootstrap_account["output"])
        self.assertIn("admin@example.com", output)
        self.assertIn("admin", output)

    def test_admin_bootstrap_rejects_bad_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "incorrect"):
            admin_bootstrap("admin@example.com", "neonpass", "bad-key", self.store)

    def test_non_admin_cannot_use_admin_commands(self) -> None:
        token, _ = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]

        output, _ = run_command_for_session(web_session, "admin users", self.store)

        self.assertIn("denied", output)


if __name__ == "__main__":
    unittest.main()
