import secrets
import time
from uuid import UUID

_RAND_B_BITS = 62


def new_id() -> UUID:
    """UUIDv7 (RFC 9562): 48 бит unix_ms, ver=7, 12 бит rand_a, var=10, 62 бита rand_b."""
    # ponytail: без счётчика внутри миллисекунды порядок id одной ms случаен;
    # нужен строгий порядок — метод 1 RFC 9562 §6.2 (12-битный счётчик в rand_a).
    unix_ms = time.time_ns() // 1_000_000
    rand = secrets.randbits(12 + _RAND_B_BITS)
    rand_a = rand >> _RAND_B_BITS
    rand_b = rand & ((1 << _RAND_B_BITS) - 1)
    return UUID(int=(unix_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b)
