"""Хэш пароля: scrypt из стандартной библиотеки (без новых зависимостей).

Формат: `scrypt$<n>$<r>$<p>$<соль hex>$<хэш hex>` — параметры хранятся в строке,
поэтому их можно усилить позже, не ломая старые хэши.
"""

import hashlib
import hmac
import secrets

MIN_LENGTH = 10
MAX_LENGTH = 256  # scrypt на мегабайтном «пароле» — дешёвый способ нагрузить CPU
_N, _R, _P = 2**14, 8, 1  # ~16 МБ памяти и десятки мс на проверку
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """False на любой неверный/повреждённый хэш — без исключений наружу."""
    if not stored or len(password) > MAX_LENGTH:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        got = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(digest) // 2,
            maxmem=2**26,
        )
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), digest)


def password_problem(password: str) -> str | None:
    """Код проблемы для ответа API или None, если пароль подходит."""
    if len(password) < MIN_LENGTH:
        return "too_short"
    if len(password) > MAX_LENGTH:
        return "too_long"
    return None
