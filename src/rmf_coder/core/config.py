from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

_DEFAULT_HOST_ = "127.0.0.1"
_DEFAULT_PORT_ = 7437
_DEFAULT_LOG_LEVEL_ = "INFO"
_DEFAULT_LOG_FILE_ = "~/.rmf_coder/core.log"
_DEFAULT_LOG_FORMAT_ = "text"
_DEFAULT_CONFIG_PATH_ = "~/.rmf_coder/config.toml"


@dataclass
class LoggingConfig:
    level: str = _DEFAULT_LOG_LEVEL_
    file: str = _DEFAULT_LOG_FILE_
    format: str = _DEFAULT_LOG_FORMAT_


@dataclass
class RMFConfig:
    host: str = _DEFAULT_HOST_
    port: int = _DEFAULT_PORT_
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def get_config() -> RMFConfig:
    config = RMFConfig()
    load_dotenv(".env", override=False)
    config_path = Path(os.environ.get("RMF_CONFIG", _DEFAULT_CONFIG_PATH_)).expanduser()

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise SystemExit(f"Config parse error ({config_path}):{e}") from e
        _apply_toml(config, data)

    _apply_env(config)
    return config


def _apply_toml(config: RMFConfig, data: dict[str, Any]) -> None:
    unknown = set(data.keys()) - {"core", "logging"}
    if unknown:
        raise SystemExit(f"Unknown top-level config keys: {', '.join(sorted(unknown))}")

    if "core" in data:
        core = data["core"]
        if not isinstance(core, dict):
            raise SystemExit("Config error: [core] must be a table")
        unknown_core: set[str] = set(core.keys()) - {"host", "port"}
        if unknown_core:
            raise SystemExit(f"Unknown [core] keys: {', '.join(sorted(unknown_core))}")
        if "host" in core:
            val = core["host"]
            if not isinstance(val, str):
                raise SystemExit("Config error: core.host must be a string")
            config.host = val
        if "port" in core:
            val = core["port"]
            if not isinstance(val, int):
                raise SystemExit("Config error: core.port must be a integer")
            config.port = val

    if "logging" in data:
        log = data["logging"]
        if not isinstance(log, dict):
            raise SystemExit("Config error: [logging] must be a table")
        unknown_log: set[str] = set(log.keys()) - {"level", "file", "format"}
        if unknown_log:
            raise SystemExit(f"Unknown [logging] keys: {', '.join(sorted(unknown_log))}")
        for key in ("level", "file", "format"):
            if key in log:
                val = log[key]
                if not isinstance(val, str):
                    raise SystemExit(f"Config error: logging.{key} must be a string")
                setattr(config.logging, key, val)


def _apply_env(config: RMFConfig) -> None:
    host = os.environ.get("RMF_HOST")
    if host is not None:
        config.host = host

    port_str = os.environ.get("RMF_PORT")
    if port_str is not None:
        try:
            config.port = int(port_str)
        except ValueError:
            raise SystemExit(f"Config error: RMF_PORT must be a integer, got: {port_str!r}")

    log_level = os.environ.get("RMF_LOG_LEVEL")
    if log_level is not None:
        config.logging.level = log_level

    log_file = os.environ.get("RMF_LOG_FILE")
    if log_file is not None:
        config.logging.file = log_file

    log_format = os.environ.get("RMF_LOG_FORMAT")
    if log_format is not None:
        config.logging.format = log_format
