# omnix-scientist for Python

Python adapter for dual-running a legacy implementation and a candidate
implementation while OMNIX collects mismatch evidence.

## Status

This package is an adapter surface for private pilots and service-side
experiments. The experiment always returns the control result; candidate drift
is reported asynchronously to the configured sink.

## Install

```bash
pip install omnix-scientist
```

For local development from this repository:

```bash
cd services/scientist-python
pip install -e ".[dev]"
```

## Quickstart

```python
from flask import jsonify, request
from omnix_scientist import Experiment, http_publisher

exp = Experiment(
    name="checkout/legacy-vs-replica",
    publisher=http_publisher("https://app.axiomcontrol.systems"),
)

@exp.use
def legacy(order):
    return legacy_checkout(order)

@exp.try_
def candidate(order):
    return new_checkout_python(order)

@app.post("/checkout")
def checkout():
    order = request.get_json()
    return jsonify(exp.run(order))
```

## Configuration

Set `OMNIX_TENANT_TOKEN` when publishing to an OMNIX tenant. For local-only
experiments, use `list_publisher` or `jsonl_publisher` so mismatches stay on
the machine running the service.

## Verification

Run package-specific tests from this directory when test dependencies are
installed:

```bash
pytest
```
