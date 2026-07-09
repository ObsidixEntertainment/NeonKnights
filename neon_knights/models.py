from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ancestry:
    key: str
    name: str
    hook: str
    trait: str


@dataclass(frozen=True)
class Faction:
    key: str
    name: str
    motto: str
    description: str


@dataclass(frozen=True)
class Augment:
    key: str
    name: str
    slot: str
    cost: int
    essence_cost: int
    description: str


@dataclass(frozen=True)
class Gear:
    key: str
    name: str
    slot: str
    cost: int
    power: int
    armor: int
    description: str


@dataclass(frozen=True)
class Skill:
    key: str
    name: str
    description: str


@dataclass(frozen=True)
class Material:
    key: str
    name: str
    description: str


@dataclass(frozen=True)
class MiningNode:
    key: str
    name: str
    material: str
    yield_amount: int
    required_level: int
    xp: int
    description: str


@dataclass(frozen=True)
class CraftRecipe:
    key: str
    name: str
    item_key: str
    materials: dict[str, int]
    required_skills: dict[str, int]
    xp: int
    description: str


@dataclass(frozen=True)
class Enemy:
    key: str
    name: str
    hp: int
    attack: int
    reward: int
    description: str


@dataclass(frozen=True)
class NPC:
    key: str
    name: str
    description: str
    dialogue: str


@dataclass(frozen=True)
class Exit:
    direction: str
    destination: str
    description: str
    required_augment: str | None = None
    required_faction: str | None = None


@dataclass(frozen=True)
class Room:
    key: str
    name: str
    description: str
    exits: tuple[Exit, ...] = ()
    npcs: tuple[NPC, ...] = ()
    augments_for_sale: tuple[str, ...] = ()
    gear_for_sale: tuple[str, ...] = ()
    mining_nodes: tuple[str, ...] = ()
    craft_recipes: tuple[str, ...] = ()
    enemies: tuple[str, ...] = ()
    scan_text: str = ""
    ascii_art: str = ""


@dataclass
class Character:
    name: str
    ancestry: str
    location: str = "redline-station"
    credits: int = 1200
    essence: int = 100
    hp: int = 30
    max_hp: int = 30
    faction: str | None = None
    augments: set[str] = field(default_factory=set)
    inventory: set[str] = field(default_factory=lambda: {"street-knife", "patchwork-coat"})
    materials: dict[str, int] = field(default_factory=dict)
    equipment: dict[str, str] = field(default_factory=lambda: {"weapon": "street-knife", "body": "patchwork-coat"})
    defeated_enemies: set[str] = field(default_factory=set)
    enemy_hp: dict[str, int] = field(default_factory=dict)
    skills_xp: dict[str, int] = field(default_factory=dict)
    tutorial_seen: bool = False

    def has_augment(self, key: str) -> bool:
        return key in self.augments

    def has_item(self, key: str) -> bool:
        return key in self.inventory
