#!/usr/bin/env python3

import os
from pathlib import Path

from whl_deploy.common import (
    execute_command,
    CommandExecutionError,
    info,
    warning,
    error,
    critical,
)

# --- Configuration Constants ---
# Use Path objects for configuration paths
CORE_DUMP_DIR_RELATIVE = Path("data/core")
CORE_DUMP_CONF_FILE = Path("/etc/sysctl.d/99-core-dump.conf")
BAZEL_CACHE_DIR = Path("/var/cache/bazel/repo_cache")
UVCVIDEO_CONF_FILE = Path("/etc/modprobe.d/uvcvideo.conf")
UDEV_RULES_SRC_DIR_RELATIVE = Path("docker/setup_host/etc/udev/rules.d")
UDEV_RULES_DEST_DIR = Path("/etc/udev/rules.d")


# --- Host Configuration Logic ---
class HostConfigManager:
    """Manages host machine configurations for the Apollo project."""

    def __init__(self):
        # Determine APOLLO_ROOT_DIR dynamically using pathlib
        # This script's location: <APOLLO_ROOT_DIR>/docker/setup_host/config_system.py
        script_dir = Path(__file__).resolve().parent
        self.apollo_root_dir = (script_dir / os.pardir / os.pardir).resolve()
        info(f"Determined APOLLO_ROOT_DIR: {self.apollo_root_dir}")

        self.core_dump_dir = self.apollo_root_dir / CORE_DUMP_DIR_RELATIVE
        self.udev_rules_src_dir = self.apollo_root_dir / UDEV_RULES_SRC_DIR_RELATIVE

    def _check_pre_conditions(self) -> None:
        """Checks essential prerequisites before starting any host setup."""
        info("Checking host setup pre-conditions...")

        if not self.apollo_root_dir.is_dir():
            raise RuntimeError(
                f"APOLLO_ROOT_DIR ('{self.apollo_root_dir}') not found or is not a directory. "
                "Please ensure this script is run from within the Apollo project structure."
            )
        info(f"APOLLO_ROOT_DIR ({self.apollo_root_dir}) detected and is valid.")

        # Check for essential commands
        # Using `which` to ensure commands exist and are in PATH.
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
        info("All required commands are available.")

    def _setup_bazel_cache_dir(self) -> None:
        """Creates and configures the Bazel cache directory."""
        info("Creating Bazel cache directory...")

        if BAZEL_CACHE_DIR.is_dir():
            info(
                f"Bazel cache directory '{BAZEL_CACHE_DIR}' already exists. Skipping creation."
            )
        else:
            execute_command(
                ["mkdir", "-p", str(BAZEL_CACHE_DIR)],
                capture_output=False,
                check=True,
                use_sudo=True,
            )
            info(f"Created Bazel cache directory: {BAZEL_CACHE_DIR}.")

        # Ensure permissions are appropriate for a shared cache (0777 or a+rwx is common for shared caches,
        # but 0755 with appropriate user/group ownership might be better if applicable. Sticking to original for consistency unless specified)
        # Re-evaluating 0777: for `/var/cache/bazel/repo_cache`, it's meant to be shared.
        # But `chmod 0777` is generally frowned upon. Let's make it more explicit if it's meant for group access.
        # Given the context, `a+rwx` (0777) is often used for this specific type of shared cache.
        # If strict security, then ensure Bazel user has access and others read-only.
        # Sticking with original intent (shared writeable) but adding comment.
        execute_command(
            ["chown", "-R", "root:docker", str(BAZEL_CACHE_DIR)],
            capture_output=False,
            check=True,
            use_sudo=True,
        )
        execute_command(
            ["chmod", "-R", "2775", str(BAZEL_CACHE_DIR)],
            capture_output=False,
            check=True,
            use_sudo=True,
        )
        info(
            f"Set permissions for '{BAZEL_CACHE_DIR}' to 2775 (group writable for shared cache)."
        )

        info("Bazel cache directory configured.")

    def setup_host_machine(self) -> int:
        """Orchestrates the host machine setup process."""
        info("Starting host machine setup process...")
        try:
            self._check_pre_conditions()
            self._setup_bazel_cache_dir()

            info("Host machine setup completed successfully!")
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
