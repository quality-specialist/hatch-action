from http import HTTPStatus
import os
from pathlib import Path
import sys
from typing import NoReturn
from urllib.parse import urlparse

import id
import requests

_GITHUB_STEP_SUMMARY = Path(os.getenv("GITHUB_STEP_SUMMARY"))

_ERROR_SUMMARY_MESSAGE = """
Trusted publishing exchange failure:

{message}

You're seeing this because the action wasn't given the inputs needed to
perform password-based or token-based authentication. If you intended to
perform one of those authentication methods instead of trusted
publishing, then you should double-check your secret configuration and variable
names.

Read more about trusted publishers at https://docs.pypi.org/trusted-publishers/

Read more about how this action uses trusted publishers at
https://github.com/marketplace/actions/pypi-publish#trusted-publishing
"""

_TOKEN_RETRIEVAL_FAILED_MESSAGE = """
OpenID Connect token retrieval failed: {identity_error}

This generally indicates a workflow configuration error, such as insufficient
permissions. Make sure that your workflow has `id-token: write` configured
at the job level, e.g.:

```yaml
permissions:
  id-token: write
```

Learn more at https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect#adding-permissions-settings.

"""

_SERVER_REFUSED_TOKEN_EXCHANGE_MESSAGE = """
Token request failed: the server refused the request for the following reasons:

{reasons}
"""

_SERVER_TOKEN_RESPONSE_MALFORMED_JSON = """
Token request failed: the index produced an unexpected
{status_code} response.

This strongly suggests a server configuration or downtime issue; wait a few minutes and try again.
"""

_SERVER_TOKEN_RESPONSE_MALFORMED_MESSAGE = """
Token response error: the index gave us an invalid response.

This strongly suggests a server configuration or downtime issue; wait a few minutes and try again.
"""

def die(msg: str) -> NoReturn:
    with _GITHUB_STEP_SUMMARY.open("a", encoding="utf-8") as io:
        print(_ERROR_SUMMARY_MESSAGE.format(message=msg), file=io)
    msg = msg.replace("\n", "%0A")
    print(f"::error::Trusted publishing exchange failure: {msg}", file=sys.stderr)
    sys.exit(1)

def debug(msg: str):
    print(f"::debug::{msg}", file=sys.stderr)

def get_normalized_input(name: str) -> str | None:
    name = f"INPUT_{name.upper()}"
    return os.getenv(name) or os.getenv(name.replace("-", "_"))

def assert_successful_audience_call(resp: requests.Response, domain: str):
    if resp.ok:
        return
    match resp.status_code:
        case HTTPStatus.FORBIDDEN:
            die(f"audience retrieval failed: repository at {domain} has trusted publishing disabled")
        case HTTPStatus.NOT_FOUND:
            die(f"audience retrieval failed: repository at {domain} does not indicate trusted publishing support")
        case other:
            status = HTTPStatus(other)
            die(f"audience retrieval failed: repository at {domain} responded with unexpected {other}: {status.phrase}")

def main():
    repository_url = get_normalized_input("repository-url")
    repository_domain = urlparse(repository_url).netloc
    token_exchange_url = f"https://{repository_domain}/_/oidc/github/mint-token"
    audience_url = f"https://{repository_domain}/_/oidc/audience"

    audience_resp = requests.get(audience_url)
    assert_successful_audience_call(audience_resp, repository_domain)

    oidc_audience = audience_resp.json()["audience"]
    debug(f"selected trusted publishing exchange endpoint: {token_exchange_url}")

    try:
        oidc_token = id.detect_credential(audience=oidc_audience)
    except id.IdentityError as identity_error:
        die(_TOKEN_RETRIEVAL_FAILED_MESSAGE.format(identity_error=identity_error))

    mint_token_resp = requests.post(token_exchange_url, json={"token": oidc_token})

    try:
        mint_token_payload = mint_token_resp.json()
    except requests.JSONDecodeError:
        die(_SERVER_TOKEN_RESPONSE_MALFORMED_JSON.format(status_code=mint_token_resp.status_code))

    if not mint_token_resp.ok:
        reasons = "\n".join(f"* `{error['code']}`: {error['description']}" for error in mint_token_payload["errors"])
        die(_SERVER_REFUSED_TOKEN_EXCHANGE_MESSAGE.format(reasons=reasons))

    pypi_token = mint_token_payload.get("token")
    if pypi_token is None:
        die(_SERVER_TOKEN_RESPONSE_MALFORMED_MESSAGE)

    print(f"::add-mask::{pypi_token}", file=sys.stderr)
    print(pypi_token)

if __name__ == "__main__":
    main()
