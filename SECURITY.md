# Security policy

## Reporting a vulnerability

Please report security issues privately, not in a public issue or pull request.

- Preferred: use **Report a vulnerability** on this repository's **Security** tab (GitHub
  private vulnerability reporting).
- Or email hello@giantoctopus.ink with "Security" in the subject.

Include what you found, how to reproduce it, and the version you tested. We aim to acknowledge
reports within a few business days and will keep you updated until the issue is resolved.

Issues in the FilingExplorer API or website itself can be reported the same way.

## Supported versions

During 0.x, only the latest released version receives fixes.

## Handling your API token

This server reads your FilingExplorer API token from the `FILING_EXPLORER_API_TOKEN`
environment variable and sends it only to the configured API URL. Do not commit the token to
an MCP client configuration file that is shared or checked into version control. If a token
is exposed, delete it at https://www.filingexplorer.com/api-keys and create a new one.
