# @omnix/scientist for Node.js

Node.js adapter for dual-running a legacy implementation and a candidate
implementation while OMNIX collects mismatch evidence.

## Status

This package is an adapter surface for private pilots and service-side
experiments. The experiment always returns the control result; candidate drift
is published asynchronously and never breaks the request path.

## Install

```bash
npm install @omnix/scientist
```

For local development from this repository:

```bash
cd services/scientist-node
npm install
npm test
```

## Usage

```ts
import { Experiment, httpPublisher } from "@omnix/scientist";

const exp = new Experiment<Order, Receipt>(
  "checkout",
  httpPublisher("https://app.axiomcontrol.systems", process.env.OMNIX_TENANT_TOKEN),
)
  .use((order) => legacyCheckout(order))
  .try((order) => newCheckoutNode(order));

app.post("/checkout", async (req, res) => {
  const result = await exp.run(req.body);
  res.json(result);
});
```

## Configuration

Pass the tenant token into `httpPublisher`; the Node adapter does not read
environment variables automatically.

## Operational Notes

- The control result is always returned to the caller.
- Mismatches are evidence for review; they do not automatically approve a cutover.
- Do not send secrets or raw customer data to a shared tenant sink.
