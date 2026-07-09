# Neon Knights

Neon Knights is a browser-first cyberpunk fantasy RPG inspired by MUD architecture: command-driven, account-backed, visual, neon-gothic, and built for supernatural characters in a living megacity.

The first playable slice includes:

- Character ancestries: Vampire, Werewolf, Witch, Wizard, Demon, Cyborg, Awakened AI, and Human Adept.
- Augments: bionic eyes, hydraulic legs, neural spellware, moon-silver bones, and more.
- Factions: Blood Court, Pack Union, Hex Grid, Chrome Synod, Synthetic Choir, and Infernal Compact.
- A small connected city district with NPCs, room descriptions, travel, scanning, faction joining, and augment installation.
- Inventory, gear, shops, starter combat, ASCII room flair, and a short tutorial.
- Ten persistent trainable skills with XP: Technical Ability, Strength, Weaponry: Firearms, Weaponry: Warfare, Augmentation, Tactics, Medic, Stalker, Cybernetics, and Occult.
- Skill-weighted combat, mining nodes, materials, and Cybernetics crafting recipes with requirements.
- Email signup/login with two character slots per account, verification codes, login notices, password reset codes, and a first-admin bootstrap flow.
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

Local browser accounts are stored in `neon_knights.sqlite3` by default. Production should set `DATABASE_URL` to a managed PostgreSQL connection string so accounts, characters, and email codes survive deploys and instance replacement.

## Admin Bootstrap And Email Auth

Set a first-admin key before launch:

```powershell
$env:NEON_KNIGHTS_ADMIN_BOOTSTRAP_KEY="your-private-first-admin-key"
```

Then open the browser app and use the Claim Admin form with:

- Admin email
- Admin password
- Bootstrap key

Bootstrap closes automatically after the first admin account exists. Admins can use in-game admin commands from the command box:

```text
admin help
admin users
admin codes
admin codes player@example.com
admin grant player@example.com
admin verify player@example.com
admin me
```

Email delivery uses SMTP when configured:

```powershell
$env:NEON_KNIGHTS_SMTP_HOST="smtp.example.com"
$env:NEON_KNIGHTS_SMTP_PORT="587"
$env:NEON_KNIGHTS_SMTP_USERNAME="smtp-user"
$env:NEON_KNIGHTS_SMTP_PASSWORD="smtp-password"
$env:NEON_KNIGHTS_MAIL_FROM="Neon Knights <no-reply@example.com>"
```

Without SMTP, the app writes `.eml` files to `mail_outbox/` so signup, login, verification, password reset, and admin emails are still testable locally. For logged-in verification flows, the browser also shows a prototype verification code when SMTP is missing; disable that with `NEON_KNIGHTS_PASS_THROUGH_CODES=0`. Password reset codes are not exposed to anonymous users. Neon Knights never emails passwords; admin emails say which email to use and remind the admin to use the password they just entered.

Or install the script entry points:

```powershell
py -m pip install -e .
neon-knights
neon-knights-admin
neon-knights-web
```

## Internal Operator Commands

These are server-side commands, not browser features:

```powershell
neon-knights-admin list-users
neon-knights-admin reset-users --confirm RESET
```

`reset-users` deletes accounts, characters, and email codes from the configured database. Use it from a controlled operator shell only.

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
skills
mine
materials
craft
craft scrap-plate
talk vexa-13
factions
join synthetic choir
augments
install bionic-eyes
admin help
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
DATABASE_URL: managed PostgreSQL connection string
```

Push the repo to GitHub, GitLab, Bitbucket, or another public Git URL, then create a Render Blueprint or Web Service from that repository. For an existing Render service, add `DATABASE_URL` from a managed PostgreSQL database plus the other `sync: false` secret environment variables in the Render dashboard.
