# Neon Knights

Neon Knights is a browser-first cyberpunk fantasy RPG inspired by MUD architecture: command-driven, account-backed, visual, neon-gothic, and built for supernatural characters in a living megacity.

The first playable slice includes:

- Character ancestries: Vampire, Werewolf, Witch, Wizard, Demon, Cyborg, Awakened AI, and Human Adept.
- Augments: bionic eyes, hydraulic legs, neural spellware, moon-silver bones, and more.
- Factions: Blood Court, Pack Union, Hex Grid, Chrome Synod, Synthetic Choir, and Infernal Compact.
- A small connected city district with NPCs, room descriptions, travel, scanning, faction joining, and augment installation.
- Inventory, gear, shops, starter combat, ASCII room flair, and a short tutorial.
- Email signup/login with two character slots per account.
- A browser mode with a neon-gothic city backdrop, a local CLI mode, and a simple TCP command server mode.

## Run Locally

From this folder:

```powershell
py -m neon_knights.cli
```

## Run In A Browser

```powershell
py -m neon_knights.web
```

Then open:

```text
http://127.0.0.1:8000
```

Local browser accounts are stored in `neon_knights.sqlite3` by default. On Render Free, local SQLite data is demo-grade because free web services do not preserve filesystem changes across restarts or deploys. Use a paid Render disk or a managed database before treating accounts as permanent.

Or install the script entry points:

```powershell
py -m pip install -e .
neon-knights
neon-knights-web
```

## Run As A Local MUD Server

```powershell
py -m neon_knights.server --host 127.0.0.1 --port 4444
```

Then connect from another terminal:

```powershell
telnet 127.0.0.1 4444
```

If Windows does not have Telnet enabled, you can still use the CLI mode above.

## Core Commands

```text
help
look
scan
go north
north
shop
buy neon-dagger
inventory
gear
equip neon-dagger
attack market-ghoul
talk vexa-13
factions
join synthetic choir
augments
install bionic-eyes
whoami
quit
```

## Development Check

```powershell
py -m unittest discover -s tests
```

## Render Deploy

This repo includes `render.yaml` for a Render Web Service.

Render settings:

```text
Build Command: pip install -e .
Start Command: python -m neon_knights.web --host 0.0.0.0
Health Check Path: /healthz
```

Push the repo to GitHub, GitLab, Bitbucket, or another public Git URL, then create a Render Blueprint or Web Service from that repository.
