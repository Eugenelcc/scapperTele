"""Validate the ``initData`` string a Telegram Web App sends to our backend.

Telegram signs the launch parameters with a key derived from the bot token, so
the backend can trust the ``user`` it receives without a login step. See:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl


class InvalidInitData(Exception):
    pass


def _secret_key(bot_token: str) -> bytes:
    # secret_key = HMAC_SHA256(key="WebAppData", message=bot_token)
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def verify_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = 86400
) -> Dict[str, Any]:
    """Return the parsed, verified fields or raise :class:`InvalidInitData`.

    ``init_data`` is the raw query-string Telegram hands to ``WebApp.initData``.
    """
    if not init_data:
        raise InvalidInitData("missing initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("missing hash")

    # Build the data-check-string: all remaining keys sorted, "key=value" per line.
    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs.keys())
    )
    computed = hmac.new(
        _secret_key(bot_token), data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise InvalidInitData("hash mismatch")

    # Reject stale launches (replay protection).
    auth_date = pairs.get("auth_date")
    if auth_date and auth_date.isdigit() and max_age_seconds > 0:
        if time.time() - int(auth_date) > max_age_seconds:
            raise InvalidInitData("initData expired")

    # Decode the JSON-encoded user object, if present.
    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError:
            pairs["user"] = None
    return pairs


def user_chat_id(verified: Dict[str, Any]) -> Optional[str]:
    """For a private chat, the user's id is the chat id we message."""
    user = verified.get("user")
    if isinstance(user, dict) and user.get("id") is not None:
        return str(user["id"])
    return None
