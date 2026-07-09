from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from neon_knights.admin import main as admin_main
from neon_knights.auth import AuthStore, normalize_database_url


class AdminCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("NEON_KNIGHTS_DB")
        self.old_database_url = os.environ.get("DATABASE_URL")
        os.environ.pop("DATABASE_URL", None)
        os.environ["NEON_KNIGHTS_DB"] = f"{self.tempdir.name}/ops.sqlite3"
        self.stores: list[AuthStore] = []

    def tearDown(self) -> None:
        for store in self.stores:
            store.close()
        restore_env("NEON_KNIGHTS_DB", self.old_db)
        restore_env("DATABASE_URL", self.old_database_url)
        self.tempdir.cleanup()

    def test_list_users_and_reset_users_are_internal_commands(self) -> None:
        store = AuthStore()
        self.stores.append(store)
        store.create_user("admin@example.com", "neonpass", is_admin=True, email_verified=True)

        list_output = run_admin("list-users")
        reset_output = run_admin("reset-users", "--confirm", "RESET")
        check_store = AuthStore()
        self.stores.append(check_store)

        self.assertIn("admin@example.com | admin | verified", list_output)
        self.assertIn("All users, characters, and email codes were reset", reset_output)
        self.assertEqual(check_store.list_users(), [])

    def test_reset_requires_exact_confirmation(self) -> None:
        with self.assertRaises(SystemExit):
            run_admin("reset-users", "--confirm", "NOPE")

    def test_postgres_url_uses_psycopg_driver(self) -> None:
        self.assertEqual(
            normalize_database_url("postgres://user:pass@host/db"),
            "postgresql+psycopg://user:pass@host/db",
        )
        self.assertEqual(
            normalize_database_url("postgresql://user:pass@host/db"),
            "postgresql+psycopg://user:pass@host/db",
        )


def run_admin(*args: str) -> str:
    output = io.StringIO()
    with redirect_stdout(output), redirect_stderr(io.StringIO()):
        exit_code = admin_main(args)
    if exit_code:
        raise AssertionError(f"Admin command failed with exit code {exit_code}")
    return output.getvalue()


def restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
