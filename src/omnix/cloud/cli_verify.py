"""Standalone CLI verb: `python -m omnix.cloud.cli_verify <receipt-url>`.

Pulls receipt + signature + pubkey from the public verifier page and verifies
the ML-DSA-65 signature locally using the pure-Python verifier.

Exit codes:
  0  signature valid
  1  signature invalid
  2  network / decode error

This sits in the cloud subpackage so it doesn't touch the locked top-level
CLI. A future PR can wire `omnix verify` into the main `omnix` entry point.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin, urlparse


def _fetch(url: str) -> bytes:
    try:
        import httpx
    except ImportError:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as f:
            return f.read()
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _normalize_base(receipt_url: str) -> tuple[str, str]:
    p = urlparse(receipt_url)
    path = p.path
    # Accept /r/<id>, /r/<id>.json, /r/<id>.sig, /verify/r/<id>, etc.
    last = path.rstrip("/").split("/")[-1]
    for suffix in (".json", ".sig", ".html"):
        if last.endswith(suffix):
            last = last[: -len(suffix)]
            break
    base = f"{p.scheme}://{p.netloc}" + path.rsplit("/", 1)[0] + "/"
    return base, last


def verify_remote(receipt_url: str, *, verbose: bool = False) -> tuple[bool, str]:
    base, receipt_id = _normalize_base(receipt_url)
    payload_url = urljoin(base, f"{receipt_id}.json")
    sig_url = urljoin(base, f"{receipt_id}.sig")
    pubkey_url = urljoin(base.replace("/r/", "/pubkey/"), receipt_id)

    if verbose:
        print(f"[fetch] {payload_url}", file=sys.stderr)
        print(f"[fetch] {sig_url}", file=sys.stderr)
        print(f"[fetch] {pubkey_url}", file=sys.stderr)

    payload_bytes = _fetch(payload_url)
    payload = json.loads(payload_bytes)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = _fetch(sig_url)
    pk = _fetch(pubkey_url)

    from omnix.receipts.verify import verify_bytes

    valid = bool(verify_bytes(pk, canonical, b"", sig))
    import hashlib

    return valid, hashlib.sha256(canonical).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnix-verify",
                                     description="Verify an OMNIX receipt by URL")
    parser.add_argument("receipt_url", help="Receipt URL (.../r/<id>[.json|.sig])")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        valid, sha = verify_remote(args.receipt_url, verbose=args.verbose)
    except Exception as exc:  # noqa: BLE001
        print(f"verify failed: {exc}", file=sys.stderr)
        return 2
    if valid:
        print(f"OK   sha256={sha}")
        return 0
    print(f"FAIL sha256={sha}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
