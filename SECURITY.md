# Security Policy

## Reporting a Vulnerability
Please report security issues privately:
- Preferred: GitHub Security Advisory for this repository
- Alternate: streamertools.dev@gmail.com

## What to Include
- Clear reproduction steps
- Affected version/tag
- Impact summary

## Sensitive Data Rules
Do not include secrets in reports:
- access tokens
- refresh tokens
- `client_secret`
- Authorization headers
- OAuth callback params or token payloads

If a secret is exposed, rotate/revoke it immediately.
