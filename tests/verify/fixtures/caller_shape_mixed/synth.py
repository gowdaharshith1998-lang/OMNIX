"""Callers pass mixed int and str for first parameters."""


def target_mix(a, b):
    return a, b


def m1():
    target_mix(1, 1)


def m2():
    target_mix("x", 2)
