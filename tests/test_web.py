from __future__ import annotations

import tempfile
import unittest

from neon_knights.auth import AuthStore
from neon_knights.web import (
    WEB_SESSIONS,
    create_character_for_session,
    login,
    run_command_for_session,
    select_character_for_session,
    signup,
)


class WebSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        WEB_SESSIONS.clear()
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = AuthStore(f"{self.tempdir.name}/test.sqlite3")

    def tearDown(self) -> None:
        WEB_SESSIONS.clear()
        self.tempdir.cleanup()

    def test_signup_character_creation_and_demon_state(self) -> None:
        token, account = signup("runner@example.com", "neonpass", self.store)
        web_session = WEB_SESSIONS[token]

        output, account = create_character_for_session(web_session, "Runner", "demon", self.store)

        self.assertTrue(account["authenticated"])
        self.assertIn("Welcome to Neon Knights", output)
        self.assertEqual(account["user"]["email"], "runner@example.com")
        self.assertEqual(account["state"]["name"], "Runner")
        self.assertEqual(account["state"]["ancestry"], "Demon")
        self.assertEqual(account["state"]["location"], "Redline Station")
        self.assertEqual(account["maxCharacters"], 2)

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


if __name__ == "__main__":
    unittest.main()
