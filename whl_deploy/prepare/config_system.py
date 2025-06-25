#!/usr/bin/env python3

import os
from pathlib import Path

from common import (
    execute_command,
    CommandExecutionError,
    info,
    warning,
    error,
    critical
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

        if os.geteuid() != 0:
            raise PermissionError(
                "This script must be run with root privileges (sudo).")

        if not self.apollo_root_dir.is_dir():
            raise RuntimeError(f"APOLLO_ROOT_DIR ('{self.apollo_root_dir}') not found or is not a directory. "
                               "Please ensure this script is run from within the Apollo project structure.")
        info(
            f"APOLLO_ROOT_DIR ({self.apollo_root_dir}) detected and is valid.")

        # Check for essential commands
        # Using `which` to ensure commands exist and are in PATH.
        required_cmds = ["sysctl", "systemctl", "udevadm",
                         "modprobe", "lsmod", "cp", "mkdir", "chmod", "tee"]
        for cmd in required_cmds:
            try:
                execute_command(["which", cmd], check=True,
                                capture_output=True, use_sudo=False)  # capture_output=True to avoid printing to console
            except (FileNotFoundError, CommandExecutionError):
                raise RuntimeError(
                    f"Required command '{cmd}' not found. Please ensure it's installed and in PATH.")
        info("All required commands are available.")

        if not self.udev_rules_src_dir.is_dir() or not list(self.udev_rules_src_dir.iterdir()):
            raise RuntimeError(f"Udev rules source directory '{self.udev_rules_src_dir}' not found or is empty. "
                               "Please ensure Apollo's udev rules are present in the expected location.")
        info("Udev rules source directory detected and contains files.")

        info("All host setup pre-conditions met.")

    def _setup_core_dump(self) -> None:
        """Configures core dump settings."""
        info("Setting up core dump format...")

        # Expected core_pattern
        core_pattern_expected = f"{self.core_dump_dir}/core_%e.%p"
        config_content = f"kernel.core_pattern = {core_pattern_expected}\n"

        # Check current sysctl value
        sysctl_value_matches = False
        try:
            sysctl_result = execute_command(
                ["sysctl", "-n", "kernel.core_pattern"], check=True, capture_output=True, use_sudo=False).stdout.strip()
            if sysctl_result == core_pattern_expected:
                sysctl_value_matches = True
                info(
                    f"Current kernel.core_pattern is already set to: {sysctl_result}")
            else:
                info(
                    f"Current kernel.core_pattern is: {sysctl_result}, expected: {core_pattern_expected}")
        except CommandExecutionError as e:
            warning(
                f"Could not check current kernel.core_pattern via sysctl: {e}. Proceeding with configuration.")

        # Create core dump directory and set permissions
        if not self.core_dump_dir.is_dir():
            execute_command(["mkdir", "-p", self.core_dump_dir],
                            capture_output=False, check=True)  # Ensure mkdir succeeds
            info(f"Created core dump directory: {self.core_dump_dir}.")
        else:
            info(f"Core dump directory '{self.core_dump_dir}' already exists.")

        # Set permissions for core dump directory (0755: rwx r-x r-x is safer than 0777)
        # Assuming the system/Apollo will manage cleanup and access within this directory.
        execute_command(["chmod", "0755", self.core_dump_dir],
                        capture_output=False, check=True)
        info(f"Set permissions for '{self.core_dump_dir}' to 0755.")

        # Write core dump configuration to file using tee
        # Always write to ensure the file exists and contains the correct configuration.
        info(f"Writing core dump configuration to {CORE_DUMP_CONF_FILE}...")
        execute_command(
            ["tee", CORE_DUMP_CONF_FILE],
            check=True,
            capture_output=False,
            input_data=config_content.encode('utf-8')
        )
        info(f"Core dump configuration written to {CORE_DUMP_CONF_FILE}.")

        # Apply sysctl configuration immediately
        info("Applying sysctl configuration...")
        execute_command(["sysctl", "-p", CORE_DUMP_CONF_FILE],
                        capture_output=False, check=True)

        info("Core dump configuration applied.")

    def _setup_bazel_cache_dir(self) -> None:
        """Creates and configures the Bazel cache directory."""
        info("Creating Bazel cache directory...")

        if BAZEL_CACHE_DIR.is_dir():
            info(
                f"Bazel cache directory '{BAZEL_CACHE_DIR}' already exists. Skipping creation.")
        else:
            execute_command(["mkdir", "-p", BAZEL_CACHE_DIR],
                            capture_output=False, check=True)
            info(f"Created Bazel cache directory: {BAZEL_CACHE_DIR}.")

        # Ensure permissions are appropriate for a shared cache (0777 or a+rwx is common for shared caches,
        # but 0755 with appropriate user/group ownership might be better if applicable. Sticking to original for consistency unless specified)
        # Re-evaluating 0777: for `/var/cache/bazel/repo_cache`, it's meant to be shared.
        # But `chmod 0777` is generally frowned upon. Let's make it more explicit if it's meant for group access.
        # Given the context, `a+rwx` (0777) is often used for this specific type of shared cache.
        # If strict security, then ensure Bazel user has access and others read-only.
        # Sticking with original intent (shared writeable) but adding comment.
        execute_command(["chmod", "0777", BAZEL_CACHE_DIR],
                        capture_output=False, check=True)
        info(
            f"Set permissions for '{BAZEL_CACHE_DIR}' to 0777 (world-writable for shared cache).")

        info("Bazel cache directory configured.")

    def _configure_ntp(self) -> None:
        """Configures NTP synchronization using systemd-timesyncd."""
        info("Configuring NTP synchronization with systemd-timesyncd...")
        service_name = "systemd-timesyncd.service"

        # Check if the service is available and try to enable/start it.
        # Attempting to enable/start it is generally idempotent.
        try:
            # Check if the service unit file exists by trying to enable it quietly.
            # systemctl enable will fail if unit file doesn't exist.
            execute_command(["systemctl", "enable", "--now", "--quiet", service_name],
                            check=True, capture_output=False, use_sudo=False)
            info(f"{service_name} enabled and started (or already active).")
        except CommandExecutionError as e:
            warning(f"{service_name} not found or failed to enable/start: {e}. "
                    "Please ensure 'systemd-timesyncd' is installed if accurate time synchronization is critical.")
            return  # Exit if the service itself doesn't seem to work

        info(f"{service_name} enabled and started for time synchronization.")

    def _apply_udev_rules(self) -> None:
        """Copies and applies udev rules."""
        info(
            f"Adding udev rules from '{self.udev_rules_src_dir}' to '{UDEV_RULES_DEST_DIR}'...")

        # Ensure destination directory exists
        if not UDEV_RULES_DEST_DIR.is_dir():
            execute_command(["mkdir", "-p", UDEV_RULES_DEST_DIR],
                            capture_output=False, check=True)
            info(
                f"Created udev rules destination directory: {UDEV_RULES_DEST_DIR}.")

        # Always copy the udev rules to ensure they are up-to-date. `cp -r` is idempotent.
        # Using `cp -r source_dir/. destination_dir/` to copy contents.
        # The `.` ensures contents are copied, not the directory itself.
        # This represents all contents of the directory
        source_pattern = self.udev_rules_src_dir / "."
        execute_command(["cp", "-r", source_pattern,
                        UDEV_RULES_DEST_DIR], capture_output=False, check=True)
        info("Udev rules copied.")

        info("Reloading udev rules and triggering devices...")
        execute_command(
            ["udevadm", "control", "--reload-rules"], capture_output=False, check=True)
        execute_command(["udevadm", "trigger"],
                        capture_output=False, check=True)
        info("Udev rules applied.")

    def _configure_uvcvideo_module(self) -> None:
        """Configures uvcvideo module options."""
        info(f"Adding uvcvideo clock configuration to {UVCVIDEO_CONF_FILE}...")

        config_content = "options uvcvideo clock=realtime\n"

        # Always write to ensure the configuration file exists and has the correct content.
        # This is idempotent.
        execute_command(
            ["tee", UVCVIDEO_CONF_FILE],
            check=True,
            capture_output=False,
            input_data=config_content.encode('utf-8')
        )
        info("uvcvideo configuration written.")

        info("Reloading uvcvideo module if loaded...")
        try:
            lsmod_output = execute_command(
                ["lsmod"], check=True, capture_output=True, use_sudo=False).stdout
            if "uvcvideo" in lsmod_output:
                info("uvcvideo module is currently loaded. Unloading...")
                execute_command(["modprobe", "-r", "uvcvideo"],
                                capture_output=False)
                info("uvcvideo module unloaded.")
            else:
                info("uvcvideo module not currently loaded. No unload needed.")
        except CommandExecutionError as e:
            warning(
                f"Could not check/unload uvcvideo module (lsmod or modprobe -r failed): {e}. Attempting to load anyway.")
        except FileNotFoundError:
            warning(
                "lsmod command not found. Cannot determine if uvcvideo module is loaded. Attempting to load anyway.")

        execute_command(["modprobe", "uvcvideo"],
                        capture_output=False, check=True)
        info("uvcvideo module configured and reloaded.")

    def setup_host_machine(self) -> int:
        """Orchestrates the host machine setup process."""
        info("Starting host machine setup process...")
        try:
            self._check_pre_conditions()
            self._setup_core_dump()
            self._setup_bazel_cache_dir()
            self._configure_ntp()
            self._apply_udev_rules()
            self._configure_uvcvideo_module()

            info("Host machine setup completed successfully!")
            return 0
        except (CommandExecutionError, FileNotFoundError, PermissionError, RuntimeError) as e:
            error(f"Host machine setup failed: {e}")
            if isinstance(e, CommandExecutionError) and (e.stdout or e.stderr):
                error(
                    "Please review the logs above for more details on the command failure.")
            return 1
        except Exception as e:
            critical(
                f"An unexpected critical error occurred during host machine setup: {e}")
            return 1
