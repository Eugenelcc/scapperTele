import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.webapp.auth import InvalidInitData, user_chat_id, verify_init_data

TOKEN = "123456:TEST_TOKEN_abcDEF"


def make_init_data(token=TOKEN, user=None, auth_date=None, tamper=False):
    """Build a correctly-signed initData string like Telegram would."""
    if user is None:
        user = {"id": 42, "first_name": "Eug", "username": "eug"}
    if auth_date is None:
        auth_date = int(time.time())
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAABBBCCC",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": 999}, separators=(",", ":"))
    fields["hash"] = h
    return urlencode(fields)


def test_valid_init_data_passes():
    init_data = make_init_data()
    verified = verify_init_data(init_data, TOKEN)
    assert verified["user"]["id"] == 42
    assert user_chat_id(verified) == "42"


def test_wrong_token_fails():
    init_data = make_init_data()
    with pytest.raises(InvalidInitData):
        verify_init_data(init_data, "999999:WRONG")


def test_tampered_payload_fails():
    init_data = make_init_data(tamper=True)
    with pytest.raises(InvalidInitData):
        verify_init_data(init_data, TOKEN)


def test_missing_hash_fails():
    with pytest.raises(InvalidInitData):
        verify_init_data("auth_date=123&user=%7B%7D", TOKEN)


def test_empty_fails():
    with pytest.raises(InvalidInitData):
        verify_init_data("", TOKEN)


def test_expired_fails():
    old = int(time.time()) - 10_000
    init_data = make_init_data(auth_date=old)
    with pytest.raises(InvalidInitData):
        verify_init_data(init_data, TOKEN, max_age_seconds=3600)
