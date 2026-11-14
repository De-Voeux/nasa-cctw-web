"""Credentials from a local, gitignored `.env` (or the process environment).

Values are never printed, logged or written anywhere. Only variable *names* are reported.
Earthdata: a user token (EARTHDATA_TOKEN) is sent as a Bearer header to Harmony only.
Copernicus Marine: the official toolbox reads COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD from
the environment, or its own ~/.copernicusmarine credentials file.
"""
from __future__ import annotations

import os
from pathlib import Path


class AuthError(RuntimeError):
    pass


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Comments, blanks and malformed lines are ignored."""
    out: dict[str, str] = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def apply_env(path: Path, environ: dict | None = None) -> list[str]:
    """Copy non-empty .env values into the environment unless already set. Returns the names set."""
    environ = os.environ if environ is None else environ
    set_names = []
    for k, v in load_dotenv(path).items():
        if v and not environ.get(k):
            environ[k] = v
            set_names.append(k)
    return set_names


def earthdata_token(environ: dict | None = None) -> str:
    environ = os.environ if environ is None else environ
    tok = (environ.get("EARTHDATA_TOKEN") or "").strip()
    if not tok:
        raise AuthError("EARTHDATA_TOKEN is not set. Put it in the gitignored .env "
                        "(generate it at urs.earthdata.nasa.gov -> Generate Token); never paste it into chat.")
    return tok


def copernicus_configured(environ: dict | None = None, home: Path | None = None) -> bool:
    environ = os.environ if environ is None else environ
    if environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"):
        return True
    home = home or Path.home()
    return any((home / ".copernicusmarine").glob("*credentials*"))
