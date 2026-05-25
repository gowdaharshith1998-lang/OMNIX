# omnix-scientist (Python)

Drop-in GitHub-Scientist port for OMNIX behavioral replication. Use it inside
your Python service to dual-run legacy and candidate implementations and
upstream every mismatch to your OMNIX tenant.

## Install

    pip install omnix-scientist

## Quickstart

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

    @app.route("/checkout", methods=["POST"])
    def checkout(order):
        return exp.run(order)

## Configuration

Set ``OMNIX_TENANT_TOKEN`` in the environment so every mismatch is upstreamed
to your tenant. To run without upstreaming (purely local logs), use
``list_publisher`` or ``jsonl_publisher``.
