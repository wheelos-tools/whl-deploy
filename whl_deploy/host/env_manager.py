#!/usr/bin/env python3

import os
from pathlib import Path
from whl_deploy.utils.common import (
    execute_command,
    CommandExecutionError,
    debug,
    info,
    warning,
    error,
    critical,
    get_os_info,
    prompt_for_choice,
)
from whl_deploy.host.config import config, load_config, save_config


class HostEnvManager:
    """Manages host machine configurations and environment setup for the Apollo project."""

    def __init__(self):
        # Determine APOLLO_ROOT_DIR dynamically using pathlib
        script_dir = Path(__file__).resolve().parent
        self.apollo_root_dir = (script_dir / os.pardir / os.pardir).resolve()

    def check_pre_conditions(self) -> None:
        """Checks essential prerequisites before starting any host setup."""
        debug("Checking host setup pre-conditions...")

        if not self.apollo_root_dir.is_dir():
            raise RuntimeError(
                f"APOLLO_ROOT_DIR ('{self.apollo_root_dir}') not found or is not a directory. "
                "Please ensure this script is run from within the Apollo project structure."
            )
        debug(f"APOLLO_ROOT_DIR ({self.apollo_root_dir}) detected and is valid.")

        # Check for essential commands
        required_cmds = [
            "sysctl",
            "systemctl",
            "udevadm",
            "modprobe",
            "lsmod",
            "cp",
            "mkdir",
            "chmod",
            "tee",
        ]
        for cmd in required_cmds:
            try:
                execute_command(["which", cmd], check=True, capture_output=True)
            except (FileNotFoundError, CommandExecutionError):
                raise RuntimeError(
                    f"Required command '{cmd}' not found. Please ensure it's installed and in PATH."
                )
        debug("All required commands are available.")

    def setup_host_machine(self) -> int:
        """Orchestrates the host machine setup process."""
        debug("Starting host machine setup process...")
        try:
            self.check_pre_conditions()
            return 0
        except (
            CommandExecutionError,
            FileNotFoundError,
            PermissionError,
            RuntimeError,
        ) as e:
            error(f"Host machine setup failed: {e}")
            if isinstance(e, CommandExecutionError) and (e.stdout or e.stderr):
                error(
                    "Please review the logs above for more details on the command failure."
                )
            return 1
        except Exception as e:
            critical(
                f"An unexpected critical error occurred during host machine setup: {e}"
            )
            return 1

    def check_host_environment(self) -> None:
        """Check and load the host environment configuration from file."""
        self.setup_host_machine()

        config_data = load_config()
        config_data["os_info"] = get_os_info()

        mirror = config_data.get("mirror_region") or prompt_for_choice(
            "Select mirror", ["CN", "US"], default="CN", auto_confirm=False
        )
        config_data["mirror_region"] = mirror
        save_config(config_data)

        # Update global config
        config.os_info = config_data["os_info"]
        config.mirror_region = mirror

        info("Host environment check passed.")
        info(f"OS information: {config.os_info}")
        info(f"Mirror region: {config.mirror_region}")
