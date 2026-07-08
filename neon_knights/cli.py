from __future__ import annotations

from .engine import GameSession
from .models import Character
from .world import ANCESTRIES


def main() -> None:
    print("Neon Knights MUD")
    print("=================")
    name = prompt_name()
    ancestry = prompt_ancestry()

    session = GameSession(Character(name=name, ancestry=ancestry))
    print()
    print(session.intro())

    while session.running:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nThe city keeps breathing after you disconnect.")
            break
        print(session.handle(raw))


def prompt_name() -> str:
    while True:
        name = input("Handle: ").strip()
        if name:
            return name
        print("Choose a handle the city can remember.")


def prompt_ancestry() -> str:
    print("\nChoose an ancestry:")
    for index, ancestry in enumerate(ANCESTRIES.values(), start=1):
        print(f"{index}. {ancestry.name} - {ancestry.hook}")

    keys = list(ANCESTRIES)
    while True:
        choice = input("Ancestry number or key: ").strip().lower()
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(keys):
                return keys[index]
        if choice in ANCESTRIES:
            return choice
        print("Pick a listed number or ancestry key.")


if __name__ == "__main__":
    main()

