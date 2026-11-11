"""Load the optional application configuration."""

import json
import logging
import os

from app_paths import migrate_legacy_file, resource_path, writable_path

logger = logging.getLogger(__name__)


def load_config(filename="config.json"):
    migrate_legacy_file(filename)
    local_path = writable_path(filename)
    path = (
        local_path
        if os.path.isfile(local_path)
        else resource_path(filename)
    )
    try:
        with open(path, "r", encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError:
        logger.warning("Configuration file not found at %s; using an empty config", path)
        return {}
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read configuration file %s", path)
        raise
    if not isinstance(config, dict):
        raise ValueError(f"Configuration file {path} must contain a JSON object")
    logger.info("Loaded configuration from %s", path)
    return config


def save_config(config, filename="config.json"):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    path = writable_path(filename)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=4)
            file.write("\n")
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
    logger.info("Saved application configuration to %s", path)


config = load_config()
