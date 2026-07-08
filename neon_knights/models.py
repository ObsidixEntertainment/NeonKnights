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
    scan_text: str = ""


@dataclass
class Character:
    name: str
    ancestry: str
    location: str = "redline-station"
    credits: int = 1200
    essence: int = 100
    faction: str | None = None
    augments: set[str] = field(default_factory=set)

    def has_augment(self, key: str) -> bool:
        return key in self.augments

