# Security Policy

## Authorized use only

webshell-mag generates and manages PHP WebShells. It is intended **only** for:

- systems you own, or
- engagements where you have explicit written authorization.

Using it against systems without permission may be illegal. The authors take no
responsibility for misuse.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Include reproduction steps, affected version, and impact.

You can expect an acknowledgement within 5 business days.

## Scope

In scope:

- cryptographic protocol flaws (v1/v2 envelope, HKDF, HMAC, replay window)
- payload generation bugs that leak credentials or break integrity
- GUI/CLI issues that could cause unintended command execution on the client
- path traversal / injection in the file and database operations

Out of scope:

- detection by AV/EDR/WAF (this is a dual-use tool, not a stealth guarantee)
- issues requiring a already-compromised host or stolen credentials
- feature requests for additional post-exploitation capability
