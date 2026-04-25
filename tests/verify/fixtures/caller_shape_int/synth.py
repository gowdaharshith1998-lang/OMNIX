"""Synthetic module: callers use only int literals to target."""


def target_merged(p, q):
    return p + q


def caller_a():
    target_merged(1, 2)


def caller_b():
    target_merged(3, 0)


def caller_c():
    target_merged(42, -1)
