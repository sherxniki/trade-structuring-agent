"""Model calls through the class app store's inference broker.

On the class app store, the platform sets WORKSHOP_BROKER_URL and WORKSHOP_RUN_TOKEN,
and model usage is paid from the visitor's class allowance. For local development,
set WORKSHOP_DEVELOPMENT_URL and WORKSHOP_DEVELOPMENT_TOKEN (from the store's
Account → Local development token) in a .env file.

The broker speaks the OpenAI-style chat completions format.
"""

import json
import os
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit
from uuid import uuid4

CONTRACT = "workshop.app.v1"

_selection = None  # cached model selection from /v1/bootstrap


def _development():
    return bool(os.environ.get("WORKSHOP_DEVELOPMENT_URL"))


def available():
    if _development():
        return bool(os.environ.get("WORKSHOP_DEVELOPMENT_TOKEN"))
    return bool(os.environ.get("WORKSHOP_BROKER_URL") and os.environ.get("WORKSHOP_RUN_TOKEN"))


def _token():
    name = "WORKSHOP_DEVELOPMENT_TOKEN" if _development() else "WORKSHOP_RUN_TOKEN"
    return os.environ[name]


def _call(path, body=None, profile=None):
    url = urlsplit(os.environ["WORKSHOP_DEVELOPMENT_URL" if _development() else "WORKSHOP_BROKER_URL"])
    if url.scheme not in ("http", "https"):
        raise ValueError("Use an HTTP or HTTPS workshop gateway.")
    connection_type = HTTPSConnection if url.scheme == "https" else HTTPConnection
    connection = connection_type(url.hostname, url.port, timeout=45)
    headers = {
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/json",
        "X-Workshop-Contract-Version": CONTRACT,
    }
    if body is not None:
        headers.update({
            "X-Workshop-Operation-ID": str(uuid4()),
            "X-Workshop-Expected-Profile": profile,
            "X-Workshop-Attempt-Limit": "1",
        })
    try:
        connection.request(
            "GET" if body is None else "POST",
            url.path.rstrip("/") + path,
            None if body is None else json.dumps(body),
            headers,
        )
        response = connection.getresponse()
        value = json.loads(response.read())
        if response.status != 200:
            raise ValueError(value.get("error", {}).get("message", f"Broker error {response.status}"))
        return value
    except Exception as exc:
        # Never leak the token in an error message.
        raise ValueError(str(exc).replace(_token(), "[redacted]")) from None
    finally:
        connection.close()


def selection():
    """Model and funding profile chosen by the platform for this visit."""
    global _selection
    if _selection is None:
        boot = _call("/v1/bootstrap")
        expected_mode = "development" if _development() else "hosted"
        if boot.get("mode") != expected_mode or boot.get("simulated") or boot.get("contractVersion") != CONTRACT:
            raise ValueError("The workshop bootstrap does not match this runtime.")
        if not _development() and boot.get("runId") != os.environ.get("WORKSHOP_RUN_ID"):
            raise ValueError("The workshop bootstrap does not match this run.")
        _selection = boot["inference"]["selection"]
    return _selection


def chat(messages, tools=None, max_tokens=800):
    """One model request. Returns the assistant message dict."""
    sel = selection()
    request = {"model": sel["modelId"], "messages": messages, "max_tokens": max_tokens}
    if tools:
        request["tools"] = tools
    response = _call("/v1/llm/chat/completions", request, sel["profileId"])
    return response["choices"][0]["message"]
