import os
import yaml
from pathlib import Path


CONFIG_PATH = os.path.expanduser("~/.config/whl_deploy/config.yaml")

WORKSPACE = Path("apollo")


def load_config() -> dict:
    """Load configuration from the YAML file."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}
    return {}


def save_config(cfg: dict) -> None:
    """Save the configuration to the YAML file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f)


class Config:
    """Global configuration for the application."""

    def __init__(self):
        self.os_info = None
        self.mirror_region = None

        self.workspace = Path().cwd


# Create a global config instance
config = Config()
