from __future__ import annotations

import unittest

from neon_knights.engine import GameSession
from neon_knights.models import Character


class GameSessionTests(unittest.TestCase):
    def make_session(self) -> GameSession:
        return GameSession(Character(name="Test", ancestry="witch"))

    def test_intro_starts_at_redline_station(self) -> None:
        session = self.make_session()

        intro = session.intro()

        self.assertIn("Redline Station", intro)
        self.assertIn("Trait:", intro)

    def test_can_move_between_rooms(self) -> None:
        session = self.make_session()

        output = session.handle("north")

        self.assertIn("Neon Bazaar", output)
        self.assertEqual(session.character.location, "neon-bazaar")

    def test_locked_rooftop_requires_hydraulic_legs(self) -> None:
        session = self.make_session()

        output = session.handle("up")

        self.assertIn("needs Hydraulic Legs", output)
        self.assertEqual(session.character.location, "redline-station")

    def test_install_augment_unlocks_rooftop(self) -> None:
        session = self.make_session()

        session.handle("north")
        session.handle("north")
        install = session.handle("install hydraulic-legs")
        session.handle("south")
        session.handle("south")
        rooftop = session.handle("up")

        self.assertIn("Installed Hydraulic Legs", install)
        self.assertIn("Rooftop Garden", rooftop)

    def test_join_faction_by_name(self) -> None:
        session = self.make_session()

        output = session.handle("join Synthetic Choir")

        self.assertIn("You swear to Synthetic Choir", output)
        self.assertEqual(session.character.faction, "synthetic-choir")

    def test_talk_to_npc(self) -> None:
        session = self.make_session()

        output = session.handle("talk vexa-13")

        self.assertIn("Vexa-13 says", output)


if __name__ == "__main__":
    unittest.main()

