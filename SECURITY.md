# Security Policy

We take the security of OMNIX seriously. Thank you for helping keep it and its
users safe.

Please report vulnerabilities **privately**. Do not open public issues for
vulnerabilities, exploit details, credentials, or customer data, and do not
disclose an issue publicly until it has been addressed.

## Supported versions

OMNIX is pre-1.0 and ships fixes only for the latest minor release line.

| Version | Supported          |
| ------- | ------------------ |
| `0.6.x` | :white_check_mark: |
| `< 0.6` | :x:                |

If you are on an older version, please upgrade to the latest `0.6.x` release
before reporting, in case the issue is already fixed.

## Reporting a vulnerability

Use **one** of these private channels:

1. **GitHub private security advisory (preferred):** open a report at
   <https://github.com/gowdaharshith1998-lang/OMNIX/security/advisories/new>.
   This keeps the discussion private and lets us coordinate a fix and disclosure.
2. **Email:** `gowdaharshith1998@gmail.com` with the subject line
   `OMNIX security report`.

Please include:

- the affected component, file, or path;
- the impact and how it could be exploited;
- reproduction steps or a proof of concept;
- the version/commit you tested; and
- any relevant logs, with secrets and customer data removed.

## Our commitment

- **Acknowledgement** within **3 business days** of your report.
- **Initial triage and severity assessment** within **10 business days**.
- We will keep you informed of remediation progress and coordinate a disclosure
  timeline with you. With your permission, we are happy to credit you once a fix
  is released.

## Safe harbor

We will not pursue or support legal action against anyone who, in good faith:

- reports a vulnerability through the private channels above;
- avoids privacy violations, data destruction, and service disruption while
  researching; and
- gives us a reasonable opportunity to remediate before any public disclosure.

This authorization covers good-faith research only; it does not permit accessing
data that is not yours, exfiltrating data, or degrading service for others.

## Security-sensitive areas

Changes and reports most often concern these subsystems:

- verification subprocess execution (running rebuilt/legacy code under gates);
- signed receipts, the signing keys, and the Merkle audit chain;
- cloud authentication and tenant isolation;
- GitHub App webhooks and their signature verification;
- the provider-key vault and any handling of API credentials;
- deployment manifests and air-gapped bundle handling.

## Licensing note

OMNIX is source-available commercial software. Submitting or acting on a security
report does not grant a license to use OMNIX commercially. See
[LICENSE](LICENSE).
