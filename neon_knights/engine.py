from __future__ import annotations

import textwrap
from collections.abc import Iterable

from .models import Augment, Character, CraftRecipe, Enemy, Exit, Gear, MiningNode, Room
from .world import (
    ANCESTRIES,
    AUGMENTS,
    CRAFT_RECIPES,
    ENEMIES,
    FACTIONS,
    GEAR,
    MATERIALS,
    MINING_NODES,
    SKILLS,
    build_rooms,
)


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
    "stats": "skills",
    "levels": "skills",
    "resource": "materials",
    "resources": "materials",
    "mat": "materials",
    "gather": "mine",
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
  9. skills            Check your trainable levels.
 10. mine              Gather materials where deposits exist.
 11. craft             Build gear when you meet the requirements.

You can type tutorial again any time.
"""


MAX_SKILL_LEVEL = 99


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
        if verb == "skills":
            return self.skills()
        if verb == "materials":
            return self.materials()
        if verb == "mine":
            return self.mine(rest)
        if verb == "craft":
            return self.craft(rest)
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
              skills / stats       Show trainable skill levels and XP.
              materials            Show gathered crafting materials.
              mine [node]          Gather local salvage or occult materials.
              craft [recipe]       List or craft local recipes.
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
        if room.mining_nodes:
            lines.append("Mineable: " + format_mining_nodes(room.mining_nodes) + ".")
        if room.craft_recipes:
            lines.append("Crafting: " + format_craft_recipes(room.craft_recipes) + ".")
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
        xp_lines = self.add_xp("tactics", 8)
        if self.character.ancestry in {"witch", "wizard", "demon", "vampire"}:
            xp_lines.extend(self.add_xp("occult", 6))
        if self.character.ancestry in {"ai", "cyborg"}:
            xp_lines.extend(self.add_xp("technical", 6))
        details.append(format_xp_lines(xp_lines))
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
            f"Combat style: {SKILLS[self.primary_combat_skill()].name}",
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

    def skills(self) -> str:
        lines = ["Skills:"]
        for skill in SKILLS.values():
            xp = self.skill_xp(skill.key)
            level = skill_level(xp)
            next_xp = xp_for_level(level + 1) if level < MAX_SKILL_LEVEL else xp
            if level >= MAX_SKILL_LEVEL:
                progress = "max"
            else:
                progress = f"{xp}/{next_xp} XP"
            lines.append(f"- {skill.name}: level {level} ({progress})")
        return "\n".join(lines)

    def materials(self) -> str:
        if not self.character.materials:
            return "Materials: empty. Try 'mine' in rooms with salvage or strange deposits."

        lines = ["Materials:"]
        for key, amount in sorted(self.character.materials.items()):
            if amount <= 0:
                continue
            material = MATERIALS.get(key)
            name = material.name if material else key
            lines.append(f"- {name} ({key}): {amount}")
        return "\n".join(lines) if len(lines) > 1 else "Materials: empty."

    def mine(self, target: str) -> str:
        if not self.room.mining_nodes:
            return "Nothing here can be mined or salvaged."

        node = find_mining_node(target, self.room.mining_nodes) if target else MINING_NODES[self.room.mining_nodes[0]]
        if node is None:
            return f"You do not see a mineable node named {target!r} here."

        cybernetics_level = self.skill_level("cybernetics")
        if cybernetics_level < node.required_level:
            return (
                f"{node.name} requires Cybernetics level {node.required_level}. "
                f"Your Cybernetics level is {cybernetics_level}."
            )

        self.character.materials[node.material] = self.character.materials.get(node.material, 0) + node.yield_amount
        xp_lines = self.add_xp("cybernetics", node.xp)
        xp_lines.extend(self.add_xp("strength", max(5, node.xp // 5)))
        if node.material == "glass-sigil":
            xp_lines.extend(self.add_xp("occult", 12))
        if node.material == "circuit-thread":
            xp_lines.extend(self.add_xp("technical", 12))

        material = MATERIALS[node.material]
        return join_blocks(
            f"You work {node.name} and recover {node.yield_amount} {material.name}.",
            self.materials(),
            format_xp_lines(xp_lines),
        )

    def craft(self, target: str) -> str:
        if not self.room.craft_recipes:
            return "No useful crafting station or recipe feed is available here."
        if not target:
            return self.craft_list()

        recipe = find_recipe(target, self.room.craft_recipes)
        if recipe is None:
            return f"You do not see a craft recipe named {target!r} here."
        if recipe.item_key in self.character.inventory:
            return f"You already own {GEAR[recipe.item_key].name}."

        missing_levels = [
            f"{SKILLS[skill].name} {level} (you have {self.skill_level(skill)})"
            for skill, level in recipe.required_skills.items()
            if self.skill_level(skill) < level
        ]
        if missing_levels:
            return "Requirements not met: " + "; ".join(missing_levels) + "."

        missing_materials = [
            f"{MATERIALS[key].name} {amount} (you have {self.character.materials.get(key, 0)})"
            for key, amount in recipe.materials.items()
            if self.character.materials.get(key, 0) < amount
        ]
        if missing_materials:
            return "Missing materials: " + "; ".join(missing_materials) + "."

        for key, amount in recipe.materials.items():
            self.character.materials[key] = self.character.materials.get(key, 0) - amount
            if self.character.materials[key] <= 0:
                del self.character.materials[key]
        self.character.inventory.add(recipe.item_key)

        xp_lines = self.add_xp("cybernetics", recipe.xp)
        for skill in recipe.required_skills:
            if skill != "cybernetics":
                xp_lines.extend(self.add_xp(skill, max(10, recipe.xp // 4)))

        item = GEAR[recipe.item_key]
        return join_blocks(
            f"Crafted {item.name}. It is now in your inventory.",
            item.description,
            format_xp_lines(xp_lines),
        )

    def craft_list(self) -> str:
        lines = [f"Crafting feed in {self.room.name}:"]
        for key in self.room.craft_recipes:
            recipe = CRAFT_RECIPES[key]
            item = GEAR[recipe.item_key]
            materials = ", ".join(
                f"{MATERIALS[material].name} x{amount}"
                for material, amount in recipe.materials.items()
            )
            requirements = ", ".join(
                f"{SKILLS[skill].name} {level}"
                for skill, level in recipe.required_skills.items()
            )
            owned = " owned" if item.key in self.character.inventory else ""
            lines.append(
                f"- {recipe.name} ({recipe.key}){owned}: {materials}; requires {requirements}. "
                f"{recipe.description}"
            )
        return "\n".join(lines)

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
        current_enemy_hp = self.character.enemy_hp.get(enemy.key, enemy.hp)
        remaining_enemy_hp = current_enemy_hp - attack_power
        xp_lines = self.add_xp("warfare", 25)
        xp_lines.extend(self.add_xp(self.primary_combat_skill(), 18))
        xp_lines.extend(self.add_xp("tactics", 8))

        if remaining_enemy_hp <= 0:
            self.character.defeated_enemies.add(enemy.key)
            self.character.enemy_hp.pop(enemy.key, None)
            self.character.credits += enemy.reward
            xp_lines.extend(self.add_xp("stalker", 14))
            return join_blocks(
                f"You strike {enemy.name} for {attack_power} damage.",
                f"{enemy.name} drops. You recover {enemy.reward} credits from the wreckage.",
                f"Credits: {self.character.credits}.",
                format_xp_lines(xp_lines),
            )

        self.character.enemy_hp[enemy.key] = remaining_enemy_hp
        self.character.hp = max(1, self.character.hp - enemy_damage)
        xp_lines.extend(self.add_xp("strength", 12))
        return join_blocks(
            f"You strike {enemy.name} for {attack_power} damage, but it keeps coming.",
            f"{enemy.name}: {remaining_enemy_hp}/{enemy.hp} HP.",
            f"{enemy.name} hits back for {enemy_damage}. Health: {self.character.hp}/{self.character.max_hp}.",
            format_xp_lines(xp_lines),
            "Keep pressure on it or upgrade your gear and skills.",
        )

    def attack_power(self) -> int:
        gear_power = sum(GEAR[key].power for key in self.character.equipment.values() if key in GEAR)
        warfare_bonus = (self.skill_level("warfare") - 1) // 2
        strength_bonus = (self.skill_level("strength") - 1) // 4
        style_bonus = (self.skill_level(self.primary_combat_skill()) - 1) // 3
        augment_bonus = 1 if self.character.has_augment("neural-spellware") else 0
        return 2 + gear_power + warfare_bonus + strength_bonus + style_bonus + augment_bonus

    def armor_rating(self) -> int:
        gear_armor = sum(GEAR[key].armor for key in self.character.equipment.values() if key in GEAR)
        strength_bonus = (self.skill_level("strength") - 1) // 2
        tactics_bonus = (self.skill_level("tactics") - 1) // 5
        return gear_armor + strength_bonus + tactics_bonus

    def primary_combat_skill(self) -> str:
        if self.character.ancestry in {"witch", "wizard", "demon", "vampire"}:
            return "occult"
        if self.character.ancestry in {"ai", "cyborg"}:
            return "technical"
        return "strength"

    def skill_xp(self, skill: str) -> int:
        if skill not in SKILLS:
            raise ValueError(f"Unknown skill: {skill}")
        return max(0, int(self.character.skills_xp.get(skill, 0)))

    def skill_level(self, skill: str) -> int:
        return skill_level(self.skill_xp(skill))

    def add_xp(self, skill: str, amount: int) -> list[str]:
        if amount <= 0:
            return []
        old_xp = self.skill_xp(skill)
        old_level = skill_level(old_xp)
        new_xp = old_xp + amount
        new_level = skill_level(new_xp)
        self.character.skills_xp[skill] = new_xp
        name = SKILLS[skill].name
        if new_level > old_level:
            return [f"{name} +{amount} XP. Level {new_level} reached."]
        return [f"{name} +{amount} XP."]

    def rest(self) -> str:
        if self.character.hp == self.character.max_hp:
            return "You are already steady."
        self.character.hp = self.character.max_hp
        xp_lines = self.add_xp("medic", 20)
        return join_blocks(
            f"You find a quiet signal shadow and recover. Health: {self.character.hp}/{self.character.max_hp}.",
            format_xp_lines(xp_lines),
        )

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
        xp_lines = self.add_xp("augmentation", 80)
        return join_blocks(
            f"Installed {augment.name}. "
            f"Credits: {self.character.credits}. Essence capacity: {self.character.essence}.",
            format_xp_lines(xp_lines),
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
            Combat style: {SKILLS[self.primary_combat_skill()].name}
            Top skills: {self.top_skills()}
            Augments: {augments}
            Gear: {equipped}
            Location: {self.room.name}
            """
        ).strip()

    def top_skills(self) -> str:
        ranked = sorted(SKILLS, key=lambda key: (self.skill_level(key), self.skill_xp(key)), reverse=True)
        return ", ".join(f"{SKILLS[key].name} {self.skill_level(key)}" for key in ranked[:3])


def normalize_command(command: str) -> str:
    return " ".join(command.strip().lower().split())


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    level = min(level, MAX_SKILL_LEVEL)
    return 50 * (level - 1) * level


def skill_level(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    while level < MAX_SKILL_LEVEL and xp >= xp_for_level(level + 1):
        level += 1
    return level


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


def find_mining_node(target: str, node_keys: Iterable[str]) -> MiningNode | None:
    target_slug = slug(target)
    return next(
        (
            MINING_NODES[key]
            for key in node_keys
            if target_slug in {MINING_NODES[key].key, slug(MINING_NODES[key].name)}
        ),
        None,
    )


def find_recipe(target: str, recipe_keys: Iterable[str]) -> CraftRecipe | None:
    target_slug = slug(target)
    return next(
        (
            CRAFT_RECIPES[key]
            for key in recipe_keys
            if target_slug in {
                CRAFT_RECIPES[key].key,
                CRAFT_RECIPES[key].item_key,
                slug(CRAFT_RECIPES[key].name),
                slug(GEAR[CRAFT_RECIPES[key].item_key].name),
            }
        ),
        None,
    )


def format_augments(keys: Iterable[str]) -> str:
    return ", ".join(f"{AUGMENTS[key].name} ({key})" for key in keys)


def format_gear(keys: Iterable[str]) -> str:
    return ", ".join(f"{GEAR[key].name} ({key})" for key in keys)


def format_mining_nodes(keys: Iterable[str]) -> str:
    return ", ".join(f"{MINING_NODES[key].name} ({key})" for key in keys)


def format_craft_recipes(keys: Iterable[str]) -> str:
    return ", ".join(f"{CRAFT_RECIPES[key].name} ({key})" for key in keys)


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


def format_xp_lines(lines: Iterable[str]) -> str:
    clean = [line for line in lines if line]
    return "Training: " + " ".join(clean) if clean else ""
