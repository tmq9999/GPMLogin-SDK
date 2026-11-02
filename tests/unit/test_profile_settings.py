from __future__ import annotations

import math
from typing import Any

import pytest

from gpmlogin_sdk import GPMValidationError
from gpmlogin_sdk._validation import validate_start
from gpmlogin_sdk.helpers.profile_settings import build_start_options, join_startup_urls


def test_build_start_options_matches_the_wire_contract() -> None:
    options = build_start_options(
        window_size=(1280, 800), window_pos=(-100, 0), skip_proxy_check=False
    )
    assert options == {
        "window_size": "1280,800",
        "window_pos": "-100,0",
        "skip_proxy_check": False,
    }
    validate_start(options)


def test_only_provided_options_are_emitted_and_false_and_empty_are_kept() -> None:
    assert build_start_options() == {}
    assert build_start_options(addition_args="") == {"addition_args": ""}
    assert build_start_options(skip_proxy_check=False) == {"skip_proxy_check": False}
    assert build_start_options(
        window_scale=0.8, remote_debugging_port=9222, addition_args="--mute-audio --x=1"
    ) == {"window_scale": 0.8, "remote_debugging_port": 9222, "addition_args": "--mute-audio --x=1"}


def test_addition_args_is_passed_through_without_escaping() -> None:
    raw = "--user-agent=\"A B\" --foo='bar baz' & echo"
    assert build_start_options(addition_args=raw)["addition_args"] == raw


def test_positions_may_be_negative_and_lists_of_two_are_accepted() -> None:
    assert build_start_options(window_pos=(-5, -10))["window_pos"] == "-5,-10"
    assert build_start_options(window_size=[800, 600])["window_size"] == "800,600"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_size": (0, 600)},
        {"window_size": (800, -1)},
        {"window_size": (800,)},
        {"window_size": (1, 2, 3)},
        {"window_size": (True, 600)},
        {"window_size": (800.0, 600)},
        {"window_size": "800,600"},
        {"window_size": 5},
        {"window_pos": (1,)},
        {"window_pos": (1, 2, 3)},
        {"window_pos": (True, 0)},
        {"window_pos": (1.5, 0)},
        {"window_pos": "1,2"},
        {"window_scale": 0},
        {"window_scale": -1.0},
        {"window_scale": math.nan},
        {"window_scale": math.inf},
        {"window_scale": True},
        {"window_scale": "0.8"},
        {"remote_debugging_port": 0},
        {"remote_debugging_port": 70000},
        {"remote_debugging_port": True},
        {"skip_proxy_check": 1},
        {"skip_proxy_check": "false"},
        {"addition_args": 5},
        {"addition_args": ["--a"]},
    ],
)
def test_build_start_options_rejects_invalid_values(kwargs: dict[str, Any]) -> None:
    with pytest.raises(GPMValidationError):
        build_start_options(**kwargs)


def test_join_startup_urls_uses_newlines() -> None:
    joined = join_startup_urls(["https://example.com", "https://example.org"])
    assert joined == "https://example.com\nhttps://example.org"
    assert join_startup_urls(("https://example.com",)) == "https://example.com"


def test_empty_list_is_an_explicit_empty_string() -> None:
    assert join_startup_urls([]) == ""


@pytest.mark.parametrize(
    "urls",
    [
        "https://example.com",
        b"https://example.com",
        {"https://example.com"},
        (u for u in ["https://example.com"]),
        [""],
        ["   "],
        ["https://a.example", ""],
        ["https://a.example\nhttps://b.example"],
        ["https://a.example\r"],
        ["https://a.example\rhttps://b.example"],
        [5],
        [None],
        None,
    ],
)
def test_join_startup_urls_rejects_bad_input(urls: Any) -> None:
    with pytest.raises(GPMValidationError):
        join_startup_urls(urls)
