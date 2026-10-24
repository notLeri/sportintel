"""`sportintel-admin`: обслуживание установки из контейнера (работает на любой ОС с Docker).

    sportintel-admin set-password <email> [--role admin|editor|researcher]

Пароль вводится без эха (getpass); без терминала — первой строкой stdin (для скриптов).
Нет пользователя — создаётся; есть — пароль заменяется, сессии остаются.
"""

import argparse
import asyncio
import getpass
import sys

from sportintel.modules.identity import public as identity
from sportintel.platform.clock import SystemClock
from sportintel.platform.config import load_settings_or_exit
from sportintel.platform.db import Database
from sportintel.platform.errors import ValidationFailed


def _password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat: "):
        print("passwords do not match", file=sys.stderr)
        raise SystemExit(1)
    return first


async def _set_password(email: str, role: str | None) -> None:
    settings = load_settings_or_exit()
    db = Database(settings.database_url, 1)
    try:
        async with db.uow() as uow:
            user = await identity.set_password(
                uow, email, _password(), SystemClock(), role=identity.Role(role) if role else None
            )
        print(f"password set for {user.email} (role: {(role or user.role.value)})")
    finally:
        await db.dispose()


def main() -> None:
    p = argparse.ArgumentParser(prog="sportintel-admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("set-password", help="set or reset a user's password (creates the user)")
    sp.add_argument("email")
    sp.add_argument("--role", choices=[r.value for r in identity.Role])
    args = p.parse_args()
    try:
        asyncio.run(_set_password(args.email.strip().lower(), args.role))
    except ValidationFailed as e:
        print(f"rejected: {e.details[0].code if e.details else e.code}", file=sys.stderr)
        raise SystemExit(1) from None
