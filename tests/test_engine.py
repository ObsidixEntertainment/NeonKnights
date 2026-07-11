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
        self.assertIn("Street tutorial", intro)

    def test_can_move_between_rooms(self) -> None:
        session = self.make_session()

        output = session.handle("north")

        self.assertIn("Neon Bazaar", output)
        self.assertEqual(session.character.location, "neon-bazaar")

    def test_city_and_world_maps_show_location_context(self) -> None:
        session = self.make_session()

        city_map = session.handle("map")
        world_map = session.handle("wmap")

        self.assertIn("REDLINE DISTRICT", city_map)
        self.assertIn("[RS] Redline Station", city_map)
        self.assertIn("Current signal: [RS] Redline Station", city_map)
        self.assertIn("NEON KNIGHTS // WORLD MAP", world_map)
        self.assertIn("Obsidix Megacity", world_map)

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

    def test_demon_ancestry_is_playable(self) -> None:
        session = GameSession(Character(name="Ash", ancestry="demon"))

        output = session.intro()

        self.assertIn("Demon", output)
        self.assertIn("Hellmark", output)

    def test_inventory_gear_and_equipping(self) -> None:
        session = self.make_session()

        inventory = session.handle("inventory")
        gear = session.handle("gear")
        session.handle("north")
        buy = session.handle("buy neon-dagger")
        equip = session.handle("equip neon-dagger")

        self.assertIn("Street Knife", inventory)
        self.assertIn("Attack power", gear)
        self.assertIn("Bought Neon Dagger", buy)
        self.assertIn("Equipped Neon Dagger", equip)
        self.assertEqual(session.character.equipment["weapon"], "neon-dagger")

    def test_combat_rewards_credits_and_tracks_defeated_enemy(self) -> None:
        session = self.make_session()

        output = session.handle("attack training-drone")

        self.assertIn("Training Drone drops", output)
        self.assertIn("training-drone", session.character.defeated_enemies)
        self.assertEqual(session.character.credits, 1240)
        self.assertGreater(session.character.skills_xp["warfare"], 0)
        self.assertGreater(session.character.skills_xp["occult"], 0)
        self.assertGreater(session.character.skills_xp["stalker"], 0)

    def test_skills_and_mining_train_over_time(self) -> None:
        session = self.make_session()

        skills = session.handle("skills")
        mine = session.handle("mine")
        materials = session.handle("materials")

        self.assertIn("Cybernetics: level 1", skills)
        self.assertIn("Scrap Alloy", mine)
        self.assertIn("Cybernetics +35 XP", mine)
        self.assertIn("Strength +7 XP", mine)
        self.assertEqual(session.character.materials["scrap-alloy"], 2)
        self.assertIn("Scrap Alloy", materials)

    def test_crafting_requires_materials_and_adds_gear(self) -> None:
        session = self.make_session()
        session.handle("mine")
        session.handle("mine")
        session.handle("north")

        craft = session.handle("craft scrap-plate")

        self.assertIn("Crafted Scrap Plate", craft)
        self.assertIn("Cybernetics +65 XP", craft)
        self.assertIn("scrap-plate", session.character.inventory)
        self.assertNotIn("scrap-alloy", session.character.materials)

    def test_crafting_respects_skill_requirements(self) -> None:
        session = self.make_session()
        session.handle("north")

        output = session.handle("craft warded-bit")

        self.assertIn("Requirements not met", output)
        self.assertIn("Cybernetics 2", output)

    def test_combat_power_uses_leveled_skills(self) -> None:
        session = self.make_session()
        base_power = session.attack_power()

        session.character.skills_xp["warfare"] = 300
        session.character.skills_xp["occult"] = 300

        self.assertGreater(session.attack_power(), base_power)

    def test_combat_tracks_partial_enemy_damage(self) -> None:
        session = self.make_session()
        session.handle("north")

        first = session.handle("attack market-ghoul")
        second = session.handle("attack market-ghoul")

        self.assertIn("Market Ghoul: 4/10 HP", first)
        self.assertIn("Market Ghoul drops", second)
        self.assertNotIn("market-ghoul", session.character.enemy_hp)
        self.assertIn("market-ghoul", session.character.defeated_enemies)


if __name__ == "__main__":
    unittest.main()
