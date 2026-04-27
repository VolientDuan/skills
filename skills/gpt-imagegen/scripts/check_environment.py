#!/usr/bin/env python3
"""Check first-run environment and configuration for GPT ImageGen."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import ssl
import sys
from pathlib import Path


MIN_PYTHON = (3, 9)
RECOMMENDED_PYTHON = (3, 10)
RECOMMENDED_BASE_URL = "https://examine.com"
PLACEHOLDER_API_KEY = "YOUR_API_KEY"
REQUIRED_MODULES = [
    "argparse",
    "base64",
    "http.client",
    "ipaddress",
    "json",
    "mimetypes",
    "os",
    "pathlib",
    "posixpath",
    "re",
    "shlex",
    "socket",
    "ssl",
    "time",
    "uuid",
]


def default_config_path(app_name: str) -> Path:
    if os.name == "nt":
        config_root = os.environ.get("APPDATA")
        if config_root:
            return Path(config_root) / app_name / "config.json"
        return Path.home() / "AppData" / "Roaming" / app_name / "config.json"
    return Path.home() / ".config" / app_name / "config.json"


DEFAULT_CONFIG_PATH = default_config_path("gpt-imagegen")
LEGACY_CONFIG_PATH = default_config_path("dcha-imagegen")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check GPT ImageGen first-run environment and configuration."
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("GPT_IMAGE_CONFIG")
        or os.environ.get("DCHA_IMAGE_CONFIG")
        or "",
        help="Optional config path to check or write.",
    )
    parser.add_argument(
        "--base-url",
        help="HTTPS API base URL to write when --write-config is used.",
    )
    parser.add_argument(
        "--api-key",
        help="API key to write when --write-config is used.",
    )
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="Write a JSON config file using --base-url and --api-key.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    return parser.parse_args()


def config_path_from_args(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(os.path.expandvars(args.config)).expanduser()
    if DEFAULT_CONFIG_PATH.exists() or not LEGACY_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    return LEGACY_CONFIG_PATH


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Config file is not valid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Config file must contain a JSON object: {path}")
    return data


def config_value(config: dict, snake_case: str, camel_case: str) -> str:
    value = config.get(snake_case)
    if value is None:
        value = config.get(camel_case)
    return value or ""


def validate_base_url(base_url: str) -> None:
    if not base_url or not base_url.strip():
        raise RuntimeError("baseUrl is required.")
    normalized = base_url.strip()
    if "://" not in normalized:
        normalized = "https://" + normalized
    if not normalized.lower().startswith("https://"):
        raise RuntimeError("baseUrl must use HTTPS.")
    authority = normalized.split("://", 1)[1].split("/", 1)[0]
    if not authority or "@" in authority:
        raise RuntimeError("baseUrl must include a hostname and no credentials.")


def validate_api_key(api_key: str) -> None:
    if not api_key or not api_key.strip():
        raise RuntimeError("apiKey is required.")
    if api_key.strip() == PLACEHOLDER_API_KEY:
        raise RuntimeError("apiKey must be replaced with a real key.")


def write_config(path: Path, base_url: str, api_key: str) -> None:
    validate_base_url(base_url)
    validate_api_key(api_key)
    data = {"baseUrl": base_url.strip(), "apiKey": api_key.strip()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def module_checks() -> list[dict]:
    checks = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
            checks.append({"name": module_name, "ok": True, "error": ""})
        except Exception as exc:
            checks.append({"name": module_name, "ok": False, "error": str(exc)})
    return checks


def python_install_hint() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "Install Python 3.9+ from python.org or with Homebrew: brew install python"
    if system == "windows":
        return "Install Python 3.9+ from python.org, Microsoft Store, or with winget install Python.Python.3.12"
    if system == "linux":
        return "Install Python 3.9+ with your package manager, such as apt, dnf, yum, pacman, or from python.org"
    return "Install Python 3.9+ from python.org for this operating system."


def collect_status(args: argparse.Namespace) -> dict:
    path = config_path_from_args(args)
    config = load_config(path)
    base_url = (
        os.environ.get("GPT_IMAGE_BASE_URL")
        or os.environ.get("DCHA_IMAGE_BASE_URL")
        or config_value(config, "base_url", "baseUrl")
    )
    api_key = (
        os.environ.get("GPT_IMAGE_API_KEY")
        or os.environ.get("DCHA_IMAGE_API_KEY")
        or config_value(config, "api_key", "apiKey")
    )
    modules = module_checks()
    tls_context = ssl.create_default_context()
    return {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "python_ok": sys.version_info >= MIN_PYTHON,
        "python_recommended": sys.version_info >= RECOMMENDED_PYTHON,
        "python_hint": python_install_hint(),
        "third_party_dependencies": [],
        "stdlib_modules_ok": all(item["ok"] for item in modules),
        "stdlib_modules": modules,
        "tls_ok": tls_context.verify_mode == ssl.CERT_REQUIRED
        and tls_context.check_hostname,
        "config_path": str(path),
        "config_exists": path.exists(),
        "base_url_configured": bool(base_url and base_url.strip()),
        "api_key_configured": bool(api_key and api_key.strip()),
        "ready": sys.version_info >= MIN_PYTHON
        and all(item["ok"] for item in modules)
        and bool(base_url and base_url.strip())
        and bool(api_key and api_key.strip()),
    }


def print_text_report(status: dict) -> None:
    print("GPT ImageGen environment check")
    print(f"- Python: {status['python_version']} ({status['python_executable']})")
    print(f"- Python 3.9+: {'OK' if status['python_ok'] else 'MISSING'}")
    print(f"- Python 3.10+ recommended: {'yes' if status['python_recommended'] else 'no'}")
    if not status["python_ok"]:
        print(f"  Guidance: {status['python_hint']}")
    print("- Third-party dependencies: none required")
    print(f"- Standard library modules: {'OK' if status['stdlib_modules_ok'] else 'MISSING'}")
    for item in status["stdlib_modules"]:
        if not item["ok"]:
            print(f"  Missing: {item['name']} ({item['error']})")
    print(f"- TLS certificate verification: {'OK' if status['tls_ok'] else 'FAILED'}")
    print(f"- Config path: {status['config_path']}")
    print(f"- Config file: {'found' if status['config_exists'] else 'not found'}")
    print(f"- baseUrl configured: {'yes' if status['base_url_configured'] else 'no'}")
    print(f"- apiKey configured: {'yes' if status['api_key_configured'] else 'no'}")
    print(f"- Ready: {'yes' if status['ready'] else 'no'}")
    if not status["ready"]:
        print("")
        print("To create config automatically:")
        print(
            "  python3 scripts/check_environment.py --write-config "
            f"--base-url {RECOMMENDED_BASE_URL} --api-key {PLACEHOLDER_API_KEY}"
        )
        print("Use python or py -3 instead of python3 on hosts where that is the launcher.")


def main() -> int:
    args = parse_args()
    config_path = config_path_from_args(args)
    if args.write_config:
        if not args.base_url or not args.api_key:
            raise RuntimeError("--write-config requires --base-url and --api-key.")
        write_config(config_path, args.base_url, args.api_key)

    status = collect_status(args)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print_text_report(status)
    return 0 if status["ready"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"check_environment.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
