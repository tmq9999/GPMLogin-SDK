from __future__ import annotations

import math

import pytest

from gpmlogin_sdk._serialization import encode_id, serialize_body, serialize_query
from gpmlogin_sdk.enums import BrowserType, SortOrder
from gpmlogin_sdk.errors import GPMValidationError


def test_query_keeps_false_zero_and_empty_string_and_drops_none() -> None:
    assert serialize_query({"active": False, "sort": 0, "search": "", "x": None}) == {
        "active": "false",
        "sort": "0",
        "search": "",
    }


def test_query_booleans_and_numbers_use_wire_spelling() -> None:
    assert serialize_query({"a": True, "scale": 0.8, "port": 9222, "e": SortOrder.NAME_ASC}) == {
        "a": "true",
        "scale": "0.8",
        "port": "9222",
        "e": "2",
    }


@pytest.mark.parametrize("bad", [[1], {"a": 1}, (1,), b"x", object(), math.nan, math.inf])
def test_query_rejects_unsupported_values(bad: object) -> None:
    with pytest.raises(GPMValidationError):
        serialize_query({"k": bad})


def test_body_preserves_empty_string_none_false_and_zero() -> None:
    assert serialize_body({"raw_proxy": "", "note": None}) == {"raw_proxy": "", "note": None}
    assert serialize_body({"a": False, "b": 0}) == {"a": False, "b": 0}


def test_body_converts_enums_to_plain_ints_and_does_not_mutate_input() -> None:
    source = {"browser_type": BrowserType.CHROME, "name": "x"}
    result = serialize_body(source)
    assert type(result["browser_type"]) is int
    assert source["browser_type"] is BrowserType.CHROME
    assert result is not source


def test_encode_id_percent_encodes_reserved_characters() -> None:
    assert encode_id("a/b ?") == "a%2Fb%20%3F"
    uuid = "37f783ac-2635-4d53-ab8d-a300c790ecdc"
    assert encode_id(uuid) == uuid
    assert encode_id("é#") == "%C3%A9%23"


@pytest.mark.parametrize("bad", ["", ".", "..", None, 5, b"x"])
def test_encode_id_rejects_empty_non_string_and_dot_segments(bad: object) -> None:
    with pytest.raises(GPMValidationError):
        encode_id(bad)  # type: ignore[arg-type]
