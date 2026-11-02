from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "verify_dist.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_dist", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_package_has_no_content_problems() -> None:
    tool = load()
    names = [
        "gpmlogin_sdk/__init__.py",
        "gpmlogin_sdk/py.typed",
        "gpmlogin_sdk/client.py",
        "gpmlogin_sdk-0.1.0.dist-info/METADATA",
    ]
    assert tool.content_problems(names) == []


def test_missing_marker_and_stray_directories_are_reported() -> None:
    tool = load()
    problems = tool.content_problems(
        ["gpmlogin_sdk/__init__.py", "gpmlogin_sdk/client.py", "tests/test_x.py"]
    )
    assert "missing gpmlogin_sdk/py.typed" in problems
    assert "unexpected tests/test_x.py" in problems


def test_package_files_ignores_metadata_and_directories() -> None:
    tool = load()
    names = ["gpmlogin_sdk/", "gpmlogin_sdk/a.py", "gpmlogin_sdk-0.1.0.dist-info/RECORD"]
    assert tool.package_files(names) == {"gpmlogin_sdk/a.py"}


def test_relative_or_missing_paths_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tool = load()
    existing = tmp_path / "a.whl"
    existing.write_bytes(b"")
    for wheel, sdist in (
        ("relative.whl", str(existing)),
        (str(tmp_path / "none.whl"), str(existing)),
    ):
        with pytest.raises(SystemExit) as caught:
            tool.main(["--wheel", wheel, "--sdist", sdist])
        assert caught.value.code != 0


def test_a_corrupt_wheel_fails_with_a_nonzero_exit(tmp_path: Path) -> None:
    tool = load()
    wheel = tmp_path / "bad.whl"
    wheel.write_bytes(b"not a zip")
    sdist = tmp_path / "bad.tar.gz"
    sdist.write_bytes(b"not a tar")
    assert tool.main(["--wheel", str(wheel), "--sdist", str(sdist)]) == 1
