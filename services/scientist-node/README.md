# @omnix/scientist (Node.js)

Drop-in GitHub-Scientist port for Node.js services migrating to OMNIX-replicated targets.

## Install

```
npm install @omnix/scientist
```

## Usage

```ts
import { Experiment, httpPublisher } from "@omnix/scientist";

const exp = new Experiment<Order, Receipt>(
  "checkout",
  httpPublisher("https://app.axiomcontrol.systems", process.env.OMNIX_TOKEN),
)
  .use((o) => legacyCheckout(o))
  .try((o) => newCheckoutNode(o));

app.post("/checkout", async (req, res) => {
  const result = await exp.run(req.body);
  res.json(result);
});
```

The experiment always returns the **control** result. Mismatches are
published asynchronously and never break the request path.
