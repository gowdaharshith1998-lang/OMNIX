# OMNIX Self-Host Receipt

Receipt:

```bash
docs/yc_evidence/omnix_self_host_5f966b6.json
```

Verify offline:

```bash
omnix axiom verify docs/yc_evidence/omnix_self_host_5f966b6.json docs/yc_evidence/omnix_self_host_5f966b6.json.sig --pubkey ~/.omnix/keys/public.pem
```

Every commit to AXIOM's own repos emits a cryptographically signed graph receipt. Verify offline with `omnix axiom verify <receipt> <sig> --pubkey ~/.omnix/keys/public.pem`. Mechanical Orchard does not do this. IBM Project Bob does not do this. Phase Change does not do this. Receipt for commit `5f966b6`: `docs/yc_evidence/omnix_self_host_5f966b6.json`.
