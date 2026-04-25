"""Fixture: encode/decode style pair in one module for invariant tests."""


def encode(n: int) -> str:
    return f"n:{n}"


def decode(s: str) -> int:
    return int(s.split(":", 1)[1])


def use_roundtrip(n: int) -> int:
    a = encode(n)
    b = decode(a)
    return b


def push(n: int) -> str:
    return f"p:{n}"


def pop_str(s: str) -> int:
    return int(s[2:])


def use_push_pop(x: int) -> int:
    t = push(x)
    u = pop_str(t)
    return u
