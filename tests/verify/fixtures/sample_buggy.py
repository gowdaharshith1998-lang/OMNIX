"""Fixture: function that fails on some generated inputs."""


def unsafe_div(x: int) -> int:
    """1 // x raises on x == 0."""
    return 1 // x
