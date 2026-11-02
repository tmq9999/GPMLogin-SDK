"""Check built distributions in a clean temporary environment. Standard library only.

    python tools/verify_dist.py --wheel C:\\abs\\gpmlogin_sdk-0.1.0-py3-none-any.whl \\
        --sdist C:\\abs\\gpmlogin_sdk-0.1.0.tar.gz [--pip-arg=--no-index --pip-arg=--find-links=DIR]

It installs the wheel (core only, no Playwright) into a throwaway venv, checks imports, the
py.typed marker and exports, then builds a wheel from the sdist and compares package contents.
Nothing is published; the temporary directory is removed afterwards. Exit code is 0 only if
every check passes. Needs access to a package index (or --pip-arg options) to fetch httpx and the
build backend.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

PACKAGE = "gpmlogin_sdk"
REQUIRED = (f"{PACKAGE}/__init__.py", f"{PACKAGE}/py.typed", f"{PACKAGE}/client.py")
FORBIDDEN_PREFIXES = ("tests/", "docs/", "examples/", ".superpowers/")

PROBE = r"""
import importlib.resources as resources
import gpmlogin_sdk
from gpmlogin_sdk import AsyncGPMClient, GPMClient, GPMIntegrationError, StartResult, BrowserType
assert gpmlogin_sdk.__version__ == "0.1.0", gpmlogin_sdk.__version__
for name in gpmlogin_sdk.__all__:
    assert hasattr(gpmlogin_sdk, name), name
assert resources.files("gpmlogin_sdk").joinpath("py.typed").is_file()
try:
    import playwright
except ImportError:
    pass
else:
    raise SystemExit("playwright must not be installed in the core-only environment")
from gpmlogin_sdk.integrations.playwright import connect
launch = StartResult(profile_id="p", remote_debugging_port=9222)
try:
    connect(launch, None, browser_kind=BrowserType.CHROME)
except GPMIntegrationError as error:
    assert "gpmlogin-sdk[playwright]" in str(error)
else:
    raise SystemExit("connect() must fail with install guidance when Playwright is missing")
GPMClient().close()
print("probe ok")
"""


def package_files(names: list[str]) -> set[str]:
    return {name for name in names if name.startswith(f"{PACKAGE}/") and not name.endswith("/")}


def content_problems(names: list[str]) -> list[str]:
    problems = [f"missing {name}" for name in REQUIRED if name not in names]
    problems += [f"unexpected {name}" for name in names if name.startswith(FORBIDDEN_PREFIXES)]
    return problems


def run(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:4])} failed:\n{result.stdout}\n{result.stderr}")


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def verify(wheel: Path, sdist: Path, pip_args: list[str]) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
    problems += [f"wheel: {issue}" for issue in content_problems(wheel_names)]
    with tempfile.TemporaryDirectory(prefix="gpm-verify-") as temp:
        root = Path(temp)
        venv = root / "venv"
        run([sys.executable, "-m", "venv", str(venv)])
        python = str(venv_python(venv))
        run([python, "-m", "pip", "install", "--no-input", *pip_args, str(wheel)])
        probe_dir = root / "probe"
        probe_dir.mkdir()
        run([python, "-I", "-c", PROBE], cwd=probe_dir)

        source = root / "sdist"
        source.mkdir()
        with tarfile.open(sdist) as archive:
            archive.extractall(source, filter="data")
        (project,) = [path for path in source.iterdir() if path.is_dir()]
        out = root / "rebuilt"
        run(
            [
                python,
                "-m",
                "pip",
                "wheel",
                "--no-input",
                "--no-deps",
                *pip_args,
                "--wheel-dir",
                str(out),
                str(project),
            ]
        )
        (rebuilt,) = list(out.glob("*.whl"))
        with zipfile.ZipFile(rebuilt) as archive:
            rebuilt_names = archive.namelist()
        if package_files(rebuilt_names) != package_files(wheel_names):
            problems.append("sdist rebuild has different package files than the wheel")
    return problems


def absolute_file(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    if not path.is_file():
        raise argparse.ArgumentTypeError("file does not exist")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=absolute_file, required=True)
    parser.add_argument("--sdist", type=absolute_file, required=True)
    parser.add_argument("--pip-arg", action="append", default=[], dest="pip_args")
    args = parser.parse_args(argv)
    try:
        problems = verify(args.wheel, args.sdist, args.pip_args)
    except (RuntimeError, ValueError, OSError, zipfile.BadZipFile, tarfile.TarError) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("wheel and sdist verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
