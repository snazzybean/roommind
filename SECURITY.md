# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in RoomMind, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Report it through [GitHub's private vulnerability reporting](https://github.com/snazzybean/roommind/security/advisories/new)
3. Include a description of the vulnerability and steps to reproduce it

We will acknowledge your report within 48 hours and work on a fix as soon as possible.

## Scope

RoomMind runs entirely locally within your Home Assistant instance. It does not connect to any external servers or cloud services. The main security considerations are:

- **WebSocket API** — All endpoints are authenticated through Home Assistant's built-in auth system
- **Store data** — Room configurations and thermal data are stored in HA's `.storage` directory with standard HA file permissions
- **No external dependencies** — The integration has zero Python dependencies beyond Home Assistant itself

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.x     | Yes       |
| < 2.0   | No        |
