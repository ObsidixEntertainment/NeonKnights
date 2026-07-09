from __future__ import annotations

import argparse
from typing import Sequence

from .auth import AuthStore, format_reset_summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Neon Knights internal operator commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-users", help="List account emails and roles.")

    reset_parser = subparsers.add_parser("reset-users", help="Reset all accounts, characters, and email codes.")
    reset_parser.add_argument(
        "--confirm",
        required=True,
        help="Must be exactly RESET. This command deletes account data.",
    )

    args = parser.parse_args(argv)
    store = AuthStore()
    try:
        return run_command(args, store, parser)
    finally:
        store.close()


def run_command(args: argparse.Namespace, store: AuthStore, parser: argparse.ArgumentParser) -> int:
    if args.command == "list-users":
        users = store.list_users()
        if not users:
            print("No users.")
            return 0
        for user in users:
            role = "admin" if user.is_admin else "user"
            verified = "verified" if user.email_verified else "unverified"
            print(f"{user.email} | {role} | {verified}")
        return 0

    if args.command == "reset-users":
        if args.confirm != "RESET":
            parser.error("reset-users requires --confirm RESET")
        print(format_reset_summary(store.reset_all_accounts()))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
