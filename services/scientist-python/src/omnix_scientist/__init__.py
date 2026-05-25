"""Drop-in Scientist port for Python services.

The runtime is identical to omnix.cloud.verify.scientist; this package is
a thin reshipped surface so customers can pip-install it without dragging
the full OMNIX cloud package in.
"""

from omnix_scientist.core import (  # noqa: F401
    Branch,
    Experiment,
    Mismatch,
    http_publisher,
    jsonl_publisher,
    list_publisher,
)

__version__ = "0.1.0"
