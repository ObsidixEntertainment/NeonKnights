from __future__ import annotations

import unittest

from neon_knights.web import run_command, start_session


class WebSessionTests(unittest.TestCase):
    def test_start_session_returns_intro_and_state(self) -> None:
        sessions = {}

        session_id, output, state = start_session("Runner", "witch", sessions)

        self.assertIn(session_id, sessions)
        self.assertIn("Welcome to Neon Knights", output)
        self.assertEqual(state["name"], "Runner")
        self.assertEqual(state["location"], "Redline Station")

    def test_web_command_updates_state(self) -> None:
        sessions = {}
        session_id, _, _ = start_session("Runner", "witch", sessions)

        output, state = run_command(session_id, "north", sessions)

        self.assertIn("Neon Bazaar", output)
        self.assertIsNotNone(state)
        self.assertEqual(state["location"], "Neon Bazaar")

    def test_quit_removes_web_session(self) -> None:
        sessions = {}
        session_id, _, _ = start_session("Runner", "witch", sessions)

        output, state = run_command(session_id, "quit", sessions)

        self.assertIn("disconnect", output)
        self.assertIsNone(state)
        self.assertNotIn(session_id, sessions)


if __name__ == "__main__":
    unittest.main()
