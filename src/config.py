import os
import yaml
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def load_config(path: str | None = None) -> dict:
    config_path = path or os.getenv("KAT_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_filters(cfg: dict, cli_overrides: dict | None = None) -> dict:
    filters = dict(cfg.get("filters", {}))
    if cli_overrides:
        for key, val in cli_overrides.items():
            if val is not None:
                filters[key] = val
    return filters


def get_universe_config(cfg: dict) -> dict:
    return cfg.get("universe", {})


def get_scoring_weights(cfg: dict, mode: str) -> dict:
    return cfg.get("scoring", {}).get(mode, {})


def get_watchlist(cfg: dict) -> list[str]:
    return cfg.get("watchlist", [])


def get_sector_mappings(cfg: dict) -> dict:
    return cfg.get("sector_mappings", {})


def get_output_config(cfg: dict) -> dict:
    return cfg.get("output", {})
