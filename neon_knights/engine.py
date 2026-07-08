from __future__ import annotations

import textwrap
from collections.abc import Iterable

from .models import Augment, Character, Enemy, Exit, Gear, Room
from .world import ANCESTRIES, AUGMENTS, ENEMIES, FACTIONS, GEAR, build_rooms


ALIASES = {
    "l": "look",
    "x": "look",
    "n": "go north",
    "s": "go south",
    "e": "go east",
    "w": "go west",
    "u": "go up",
    "d": "go down",
    "i": "whoami",
    "inv": "inventory",
    "eq": "gear",
    "equipment": "gear",
    "store": "shop",
    "market": "shop",
    "fight": "attack",
    "a": "attack",
    "art": "ascii",
}


NEON_KNIGHTS_ASCII = r"""
 _   _                 _  __      _       _     _
| \ | | ___  ___  _ __| |/ /_ __ (_) __ _| |__ | |_ ___
|  \| |/ _ \/ _ \| '_ \ ' /| '_ \| |/ _` | '_ \| __/ __|
| |\  |  __/ (_) | | | . \| | | | | (_| | | | | |_\__ \
|_| \_|\___|\___/|_| |_|\_\_| |_|_|\__, |_| |_|\__|___/
                                   |___/
"""


TUTORIAL_TEXT = """
Street tutorial:
  1. look              Read the room and exits.
  2. scan              Notice hidden magic, tech, heat, scent, or code.
  3. north             Move to Neon Bazaar.
  4. shop              See gear and augment vendors.
  5. buy neon-dagger   Buy a starter weapon.
  6. inventory         Check what you carry.
  7. equip neon-dagger Equip the weapon.
  8. attack market-ghoul Try basic combat.

You can type tutorial again any time.
"""


class GameSession:
    def __init__(self, character: Character):
        if character.ancestry not in ANCESTRIES:
            raise ValueError(f"Unknown ancestry: {character.ancestry}")
        self.character = character
        self.rooms = build_rooms()
        self.running = True

    @property
    def room(self) -> Room:
        return self.rooms[self.character.location]

    def intro(self) -> str:
        ancestry = ANCESTRIES[self.character.ancestry]
        self.character.tutorial_seen = True
        return join_blocks(
            NEON_KNIGHTS_ASCII,
            f"Welcome to Neon Knights, {self.character.name}.",
            f"You are a {ancestry.name}. {ancestry.hook}",
            f"Trait: {ancestry.trait}",
            TUTORIAL_TEXT,
            self.look(),
        )

    def handle(self, raw_command: str) -> str:
        command = normalize_command(raw_command)
        command = ALIASES.get(command, command)
        if not command:
            return "Enter a command. Try 'help'."

        verb, _, rest = command.partition(" ")
        rest = rest.strip()

        if verb in {"quit", "exit"}:
            self.running = False
            return "The city keeps breathing after you disconnect."
        if verb == "help":
            return self.help()
        if verb == "tutorial":
            self.character.tutorial_seen = True
            return TUTORIAL_TEXT.strip()
        if verb == "ascii":
            return self.ascii()
        if verb == "look":
            return self.look()
        if verb == "scan":
            return self.scan()
        if verb == "go":
            return self.go(rest)
        if verb in {"north", "south", "east", "west", "up", "down"}:
            return self.go(verb)
        if verb == "talk":
            return self.talk(rest)
        if verb == "factions":
            return self.factions()
        if verb == "join":
            return self.join_faction(rest)
        if verb == "augments":
            return self.augments()
        if verb == "install":
            return self.install(rest)
        if verb == "shop":
            return self.shop()
        if verb == "buy":
            return self.buy(rest)
        if verb == "inventory":
            return self.inventory()
        if verb == "gear":
            return self.gear()
        if verb == "equip":
            return self.equip(rest)
        if verb == "attack":
            return self.attack(rest)
        if verb == "rest":
            return self.rest()
        if verb == "whoami":
            return self.whoami()

        return f"Unknown command: {raw_command!r}. Try 'help'."

    def help(self) -> str:
        return textwrap.dedent(
            """
            Commands:
              look / l             Show the current room.
              scan                 Read hidden signals, magic, heat, scent, or code.
              go <direction>       Move through an exit. Shortcuts: n, s, e, w, u, d.
              talk <npc>           Speak with a named NPC.
              ascii / art          Show room ASCII art.
              tutorial             Show the starter tutorial.
              shop                 List gear and augments for sale here.
              buy <gear>           Buy a gear item from this room.
              inventory / inv      Show carried gear.
              gear / equipment     Show equipped gear and stats.
              equip <gear>         Equip carried gear.
              attack <enemy>       Fight an enemy in the current room.
              rest                 Recover health at a safe spot.
              factions             List factions.
              join <faction>       Join a faction by key or name.
              augments             List augments for sale in this room.
              install <augment>    Buy and install an augment sold here.
              whoami / i           Show your character sheet.
              quit                 Disconnect.
            """
        ).strip()

    def look(self) -> str:
        room = self.room
        lines = [f"{room.name}", room.description]

        if room.ascii_art:
            lines.append(room.ascii_art)
        if room.npcs:
            lines.append("People here: " + ", ".join(npc.name for npc in room.npcs) + ".")
        enemies = self.available_enemies()
        if enemies:
            lines.append("Threats here: " + ", ".join(enemy.name for enemy in enemies) + ".")
        if room.gear_for_sale:
            lines.append("Gear for sale: " + format_gear(room.gear_for_sale) + ".")
        if room.augments_for_sale:
            lines.append("Augments for sale: " + format_augments(room.augments_for_sale) + ".")
        lines.append("Exits: " + format_exits(room.exits, self.character) + ".")
        return join_blocks(*lines)

    def ascii(self) -> str:
        return self.room.ascii_art.strip() if self.room.ascii_art else "No local ASCII signal resolves here."

    def scan(self) -> str:
        ancestry = ANCESTRIES[self.character.ancestry]
        details = [f"{ancestry.trait}", self.room.scan_text or "The room refuses to give up more."]

        if self.character.has_augment("bionic-eyes"):
            details.append("Bionic Eyes overlay: hidden thermal edges, ward seams, and machine IDs sharpen into view.")
        if self.character.has_augment("neural-spellware"):
            details.append("Neural Spellware hums as nearby rituals compile into readable intent.")
        if self.character.has_augment("synth-heart"):
            details.append("Synth Heart telemetry marks stress, adrenaline, coolant pressure, and blood rhythm.")
        return join_blocks(*details)

    def go(self, direction: str) -> str:
        if not direction:
            return "Go where?"

        exit_ = find_exit(self.room.exits, direction)
        if exit_ is None:
            return f"No exit leads {direction} from {self.room.name}."

        blocked = self.blocked_reason(exit_)
        if blocked:
            return blocked

        self.character.location = exit_.destination
        return self.look()

    def blocked_reason(self, exit_: Exit) -> str | None:
        if exit_.required_augment and not self.character.has_augment(exit_.required_augment):
            augment = AUGMENTS[exit_.required_augment]
            return (
                f"The way {exit_.direction} needs {augment.name}. "
                f"{exit_.description}"
            )
        if exit_.required_faction and self.character.faction != exit_.required_faction:
            faction = FACTIONS[exit_.required_faction]
            return f"The way {exit_.direction} is held for members of {faction.name}."
        return None

    def talk(self, target: str) -> str:
        if not target:
            return "Talk to whom?"

        target_key = slug(target)
        for npc in self.room.npcs:
            if target_key in {npc.key, slug(npc.name)}:
                return join_blocks(npc.description, npc.dialogue)
        return f"You do not see {target!r} here."

    def factions(self) -> str:
        lines = []
        for faction in FACTIONS.values():
            lines.append(f"{faction.name} ({faction.key})")
            lines.append(f"  {faction.motto}")
            lines.append(f"  {faction.description}")
        return "\n".join(lines)

    def join_faction(self, target: str) -> str:
        if not target:
            return "Join which faction? Try 'factions'."

        faction = find_faction(target)
        if faction is None:
            return f"Unknown faction: {target!r}. Try 'factions'."

        if self.character.faction == faction.key:
            return f"You are already sworn to {faction.name}."

        old = self.character.faction
        self.character.faction = faction.key
        if old:
            return f"You leave {FACTIONS[old].name} and swear to {faction.name}. {faction.motto}"
        return f"You swear to {faction.name}. {faction.motto}"

    def augments(self) -> str:
        if not self.room.augments_for_sale:
            return "No one in this room is selling augments."

        lines = [f"Augments for sale in {self.room.name}:"]
        for key in self.room.augments_for_sale:
            augment = AUGMENTS[key]
            owned = " installed" if key in self.character.augments else ""
            lines.append(
                f"- {augment.name} ({augment.key}){owned}: {augment.cost} credits, "
                f"{augment.essence_cost} essence. {augment.description}"
            )
        return "\n".join(lines)

    def shop(self) -> str:
        lines = [f"Shop feed in {self.room.name}:"]
        if self.room.gear_for_sale:
            lines.append("Gear:")
            for key in self.room.gear_for_sale:
                item = GEAR[key]
                owned = " owned" if key in self.character.inventory else ""
                lines.append(
                    f"- {item.name} ({item.key}){owned}: {item.cost} credits, "
                    f"slot {item.slot}, power {item.power}, armor {item.armor}. {item.description}"
                )
        if self.room.augments_for_sale:
            lines.append("Augments:")
            for key in self.room.augments_for_sale:
                augment = AUGMENTS[key]
                owned = " installed" if key in self.character.augments else ""
                lines.append(
                    f"- {augment.name} ({augment.key}){owned}: {augment.cost} credits, "
                    f"{augment.essence_cost} essence. {augment.description}"
                )
        if len(lines) == 1:
            return "No one is selling gear or augments here."
        return "\n".join(lines)

    def buy(self, target: str) -> str:
        if not target:
            return "Buy what? Try 'shop'."

        item = find_gear(target)
        if item is None:
            return f"Unknown gear: {target!r}."
        if item.key not in self.room.gear_for_sale:
            return f"{item.name} is not sold in {self.room.name}."
        if item.key in self.character.inventory:
            return f"You already own {item.name}."
        if self.character.credits < item.cost:
            return f"You need {item.cost} credits for {item.name}. You have {self.character.credits}."

        self.character.credits -= item.cost
        self.character.inventory.add(item.key)
        return f"Bought {item.name}. Credits: {self.character.credits}."

    def inventory(self) -> str:
        if not self.character.inventory:
            return "Inventory: empty."

        lines = ["Inventory:"]
        for key in sorted(self.character.inventory):
            item = GEAR[key]
            equipped = " equipped" if self.character.equipment.get(item.slot) == key else ""
            lines.append(
                f"- {item.name} ({item.key}){equipped}: slot {item.slot}, "
                f"power {item.power}, armor {item.armor}. {item.description}"
            )
        return "\n".join(lines)

    def gear(self) -> str:
        attack = self.attack_power()
        armor = self.armor_rating()
        lines = [
            "Equipped gear:",
            f"Health: {self.character.hp}/{self.character.max_hp}",
            f"Attack power: {attack}",
            f"Armor rating: {armor}",
        ]
        for slot in ("weapon", "body", "charm"):
            key = self.character.equipment.get(slot)
            item = GEAR[key] if key else None
            lines.append(f"- {slot}: {item.name if item else 'empty'}")
        return "\n".join(lines)

    def equip(self, target: str) -> str:
        if not target:
            return "Equip what? Try 'inventory'."

        item = find_gear(target)
        if item is None:
            return f"Unknown gear: {target!r}."
        if item.key not in self.character.inventory:
            return f"You do not own {item.name}. Try 'shop' and 'buy {item.key}'."

        previous = self.character.equipment.get(item.slot)
        self.character.equipment[item.slot] = item.key
        if previous == item.key:
            return f"{item.name} is already equipped."
        old = f" replacing {GEAR[previous].name}" if previous else ""
        return f"Equipped {item.name} in {item.slot}{old}."

    def available_enemies(self) -> list[Enemy]:
        return [
            ENEMIES[key]
            for key in self.room.enemies
            if key not in self.character.defeated_enemies
        ]

    def attack(self, target: str) -> str:
        enemies = self.available_enemies()
        if not enemies:
            return "There is nothing hostile here right now."

        enemy = find_enemy(target, enemies) if target else enemies[0]
        if enemy is None:
            return f"You do not see {target!r} here."

        attack_power = self.attack_power()
        armor = self.armor_rating()
        enemy_damage = max(1, enemy.attack - armor)
        remaining_enemy_hp = enemy.hp - attack_power

        if remaining_enemy_hp <= 0:
            self.character.defeated_enemies.add(enemy.key)
            self.character.credits += enemy.reward
            return join_blocks(
                f"You strike {enemy.name} for {attack_power} damage.",
                f"{enemy.name} drops. You recover {enemy.reward} credits from the wreckage.",
                f"Credits: {self.character.credits}.",
            )

        self.character.hp = max(1, self.character.hp - enemy_damage)
        return join_blocks(
            f"You strike {enemy.name} for {attack_power} damage, but it keeps coming.",
            f"{enemy.name} hits back for {enemy_damage}. Health: {self.character.hp}/{self.character.max_hp}.",
            "This prototype resolves enemies in one decisive hit once your gear is strong enough.",
        )

    def attack_power(self) -> int:
        return 2 + sum(GEAR[key].power for key in self.character.equipment.values() if key in GEAR)

    def armor_rating(self) -> int:
        return sum(GEAR[key].armor for key in self.character.equipment.values() if key in GEAR)

    def rest(self) -> str:
        if self.character.hp == self.character.max_hp:
            return "You are already steady."
        self.character.hp = self.character.max_hp
        return f"You find a quiet signal shadow and recover. Health: {self.character.hp}/{self.character.max_hp}."

    def install(self, target: str) -> str:
        if not target:
            return "Install which augment? Try 'augments'."

        augment = find_augment(target)
        if augment is None:
            return f"Unknown augment: {target!r}."
        if augment.key not in self.room.augments_for_sale:
            return f"{augment.name} is not sold in {self.room.name}."
        if augment.key in self.character.augments:
            return f"{augment.name} is already installed."
        if self.character.credits < augment.cost:
            return f"You need {augment.cost} credits for {augment.name}. You have {self.character.credits}."
        if self.character.essence < augment.essence_cost:
            return f"You need {augment.essence_cost} essence capacity for {augment.name}. You have {self.character.essence}."

        self.character.credits -= augment.cost
        self.character.essence -= augment.essence_cost
        self.character.augments.add(augment.key)
        return (
            f"Installed {augment.name}. "
            f"Credits: {self.character.credits}. Essence capacity: {self.character.essence}."
        )

    def whoami(self) -> str:
        ancestry = ANCESTRIES[self.character.ancestry]
        faction = FACTIONS[self.character.faction].name if self.character.faction else "Unaffiliated"
        augments = ", ".join(AUGMENTS[key].name for key in sorted(self.character.augments)) or "None"
        equipped = ", ".join(
            f"{slot}: {GEAR[key].name}"
            for slot, key in sorted(self.character.equipment.items())
            if key in GEAR
        ) or "None"
        return textwrap.dedent(
            f"""
            {self.character.name}
            Ancestry: {ancestry.name}
            Faction: {faction}
            Health: {self.character.hp}/{self.character.max_hp}
            Credits: {self.character.credits}
            Essence capacity: {self.character.essence}
            Augments: {augments}
            Gear: {equipped}
            Location: {self.room.name}
            """
        ).strip()


def normalize_command(command: str) -> str:
    return " ".join(command.strip().lower().split())


def slug(value: str) -> str:
    return normalize_command(value).replace(" ", "-")


def find_exit(exits: Iterable[Exit], direction: str) -> Exit | None:
    direction = normalize_command(direction)
    return next((exit_ for exit_ in exits if exit_.direction == direction), None)


def find_faction(target: str):
    target_slug = slug(target)
    return next(
        (
            faction
            for faction in FACTIONS.values()
            if target_slug in {faction.key, slug(faction.name)}
        ),
        None,
    )


def find_augment(target: str) -> Augment | None:
    target_slug = slug(target)
    return next(
        (
            augment
            for augment in AUGMENTS.values()
            if target_slug in {augment.key, slug(augment.name)}
        ),
        None,
    )


def find_gear(target: str) -> Gear | None:
    target_slug = slug(target)
    return next(
        (
            gear
            for gear in GEAR.values()
            if target_slug in {gear.key, slug(gear.name)}
        ),
        None,
    )


def find_enemy(target: str, enemies: Iterable[Enemy]) -> Enemy | None:
    target_slug = slug(target)
    return next(
        (
            enemy
            for enemy in enemies
            if target_slug in {enemy.key, slug(enemy.name)}
        ),
        None,
    )


def format_augments(keys: Iterable[str]) -> str:
    return ", ".join(f"{AUGMENTS[key].name} ({key})" for key in keys)


def format_gear(keys: Iterable[str]) -> str:
    return ", ".join(f"{GEAR[key].name} ({key})" for key in keys)


def format_exits(exits: Iterable[Exit], character: Character) -> str:
    visible = []
    for exit_ in exits:
        marker = ""
        if exit_.required_augment and not character.has_augment(exit_.required_augment):
            marker = f" [{AUGMENTS[exit_.required_augment].name} needed]"
        if exit_.required_faction and character.faction != exit_.required_faction:
            marker = f" [{FACTIONS[exit_.required_faction].name} only]"
        visible.append(f"{exit_.direction}{marker}")
    return ", ".join(visible) if visible else "none"


def join_blocks(*blocks: str) -> str:
    return "\n\n".join(block.strip() for block in blocks if block and block.strip())
