# Compliance: P21

"""OMNIX CLI: `omnix axiom` (ML-DSA-65) and future subcommands."""

from __future__ import annotations

import click

from axiom.cli import axiom_group


@click.group()
@click.version_option(version="0.1.0", prog_name="omnix")
def main() -> None:
    """OMNIX — code intelligence and AXIOM provenance."""


main.add_command(axiom_group, name="axiom")


if __name__ == "__main__":
    main()
