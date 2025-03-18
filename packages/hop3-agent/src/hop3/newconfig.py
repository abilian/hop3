from __future__ import annotations

import re
from pathlib import Path

from hop3.lib.config import Config

# if Path(".env").exists():
#     env_file = ".env"
# else:
#     env_file = None

config = Config()


def get_parameters():
    _vars = globals()
    result = {}
    for key in _vars:
        if re.match("[A-Z_]+$", key):
            result[key] = _vars[key]
    return result


#
#
# _toml_config: dict[str, Any] = {}
# _toml_config_path = os.environ.get("HOP3_CONFIG_FILE")
# if _toml_config_path:
#     try:
#         _toml_config = toml.load(_toml_config_path)
#     except (FileNotFoundError, toml.TomlDecodeError) as e:
#         print(f"Error loading TOML file '{_toml_config_path}': {e}", file=sys.stderr)
#         # We don't exit here; we still want to load env vars and defaults.
#
#
# def _get_config_value(key: str, cast: type | None = None, default: Any = None) -> Any:
#     """Get a config value, checking environment, .env, and TOML."""
#     # 1. Try environment variables
#     if key in _environ:
#         return _environ.get(key, cast=cast, default=default)
#
#     # 2. Try .env (using Starlette's Config for .env parsing)
#     if key in _env_config:
#         return _env_config(key, cast=cast, default=default)
#
#     # 3. Try TOML config.
#     keys = key.split(".")
#     value = _toml_config
#     for sub_key in keys:
#         if isinstance(value, dict) and sub_key in value:
#             value = value[sub_key]
#         else:
#             value = None
#             break
#     if value is not None:
#         if cast is not None:
#             try:
#                 return cast(value)
#             except (ValueError, TypeError) as e:
#                 raise ValueError(
#                     f"Could not cast value '{value}' of '{key}' to {cast}: {e}"
#                 ) from e
#         return value
#
#     # 4. Return default
#     return default
#
#
# # --- Define configuration variables ---
#
# # Main directories for Hop3.
# HOP3_ROOT: Path = Path(_get_config_value("HOP3_ROOT", default="/home/hop3"))
# HOP3_USER: str = _get_config_value("HOP3_USER", default="hop3")
# HOP3_BIN: Path = Path(_get_config_value("HOP3_BIN", default=str(HOP3_ROOT / "bin")))
# HOP3_SCRIPT: str = _get_config_value(
#     "HOP3_SCRIPT", default=str(HOP3_ROOT / "venv" / "bin" / "hop-agent")
# )
# APP_ROOT: Path = Path(_get_config_value("APP_ROOT", default=str(HOP3_ROOT / "apps")))
#
# # NGINX config
# NGINX_ROOT: Path = Path(_get_config_value("NGINX_ROOT", default=str(HOP3_ROOT / "nginx")))
# CACHE_ROOT: Path = Path(_get_config_value("CACHE_ROOT", default=str(HOP3_ROOT / "cache")))
#
# # UWSGI config
# UWSGI_ROOT: Path = Path(_get_config_value("UWSGI_ROOT", default=str(HOP3_ROOT / "uwsgi")))
# UWSGI_AVAILABLE: Path = Path(
#     _get_config_value("UWSGI_AVAILABLE", default=str(HOP3_ROOT / "uwsgi-available"))
# )
# UWSGI_ENABLED: Path = Path(
#     _get_config_value("UWSGI_ENABLED", default=str(HOP3_ROOT / "uwsgi-enabled"))
# )
# UWSGI_LOG_MAXSIZE: str = _get_config_value("UWSGI_LOG_MAXSIZE", default="1048576")
#
# # ACME (letsencrypt) config
# ACME_ROOT: Path = Path(_get_config_value("ACME_ROOT", default=str(HOP3_ROOT / ".acme.sh")))
# ACME_WWW: Path = Path(_get_config_value("ACME_WWW", default=str(HOP3_ROOT / "acme")))
# ACME_ROOT_CA: str = _get_config_value("ACME_ROOT_CA", default="letsencrypt.org")
#
# # Misc
# ROOT_DIRS: list[Path] = [
#     APP_ROOT,
#     CACHE_ROOT,
#     UWSGI_ROOT,
#     UWSGI_AVAILABLE,
#     UWSGI_ENABLED,
#     NGINX_ROOT,
# ]
#
# CRON_REGEXP: str = _get_config_value(
#     "CRON_REGEXP",
#     default=(
#         r"^((?:(?:\*\/)?\d+)|\*) "
#         r"((?:(?:\*\/)?\d+)|\*) "
#         r"((?:(?:\*\/)?\d+)|\*) "
#         r"((?:(?:\*\/)?\d+)|\*) "
#         r"((?:(?:\*\/)?\d+)|\*) "
#         r"(.*)$"
#     ),
# )
