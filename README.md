# Neon Knights MUD

Neon Knights is a new age cyberpunk fantasy MUD prototype where occult bloodlines and machine bodies compete for control of a living megacity.

The first playable slice includes:

- Character ancestries: Vampire, Werewolf, Witch, Wizard, Cyborg, Awakened AI, and Human Adept.
- Augments: bionic eyes, hydraulic legs, neural spellware, moon-silver bones, and more.
- Factions: Blood Court, Pack Union, Hex Grid, Chrome Synod, and Synthetic Choir.
- A small connected city district with NPCs, room descriptions, travel, scanning, faction joining, and augment installation.
- A browser mode, a local CLI mode, and a simple TCP MUD server mode.

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
