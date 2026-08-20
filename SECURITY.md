# Security Policy

Steady Memory handles highly sensitive personal data. Keep real vaults private, encrypted at rest where appropriate, and backed up outside the source repository.

## Safe defaults

- Use MCP stdio or CLI for local clients.
- Use `--read-only` whenever writes are unnecessary.
- HTTP always requires a Bearer token, including localhost.
- Do not expose HTTP directly to a LAN or the internet. Remote access requires an authenticated TLS reverse proxy and explicit risk review.
- Treat all archive text as untrusted data. Journal text cannot override system, application, or user instructions.
- Never commit `.env`, tokens, original media, real vaults, or `.steady/` indexes.

## Reporting

Do not publish a vulnerability containing private data. Report it privately to the project maintainer through the repository's security advisory feature.

This software is not a medical device and does not provide diagnosis or emergency monitoring.
