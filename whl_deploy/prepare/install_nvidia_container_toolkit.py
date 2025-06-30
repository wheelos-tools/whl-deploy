#!/usr/bin/env python3

import os
import platform
import re
from pathlib import Path
from whl_deploy.common import (
    get_os_info,
    execute_command,
    CommandExecutionError,
    info,
    warning,
    error,
    critical
)

# --- Configuration Constants ---
NVIDIA_TOOLKIT_KEYRING = "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
NVIDIA_TOOLKIT_LIST = "/etc/apt/sources.list.d/nvidia-container-toolkit.list"
# Default version if dynamic lookup fails or for fallback.
# Will be overridden by dynamic lookup if successful.
# Kept as a reasonable default/fallback
DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION = "1.17.8-1"

# Official upstream URL for the toolkit repository
OFFICIAL_NVIDIA_REPO_BASE_URL = "https://nvidia.github.io/libnvidia-container"
# USTC mirror URL for the toolkit repository
USTC_NVIDIA_REPO_BASE_URL = "https://mirrors.ustc.edu.cn/nvidia-container-toolkit"


# --- Helper Function for China Network Check ---
def get_repo_base_url(mirror_region: str) -> str:
    """
    Determines the base URL for the NVIDIA Container Toolkit repository
    based on whether a China mirror should be used.
    """
    if mirror_region == 'cn':
        info(f"Using China mirror repository: {USTC_NVIDIA_REPO_BASE_URL}")
        return USTC_NVIDIA_REPO_BASE_URL
    else:
        info(
            f"Using official NVIDIA repository: {OFFICIAL_NVIDIA_REPO_BASE_URL}")
        return OFFICIAL_NVIDIA_REPO_BASE_URL


# --- NVIDIA Container Toolkit Logic ---
class NvidiaToolkitManager:
    """Manages NVIDIA Container Toolkit installation and uninstallation on Ubuntu systems."""

    def __init__(self, mirror_region: str ):
        self.os_info = get_os_info()
        self.arch = platform.machine()
        self.arch_alias = self._get_arch_alias()
        # Initialize toolkit version, will be dynamically fetched during installation
        self.toolkit_version = DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION
        self.mirror_region = mirror_region.lower()
        # Set the base URL based on constructor arg
        self.repo_base_url = get_repo_base_url(self.mirror_region)

    def _get_arch_alias(self) -> str:
        """Determines the NVIDIA Container Toolkit-compatible architecture alias."""
        if self.arch == "x86_64":
            return "amd64"
        elif self.arch == "aarch64":
            return "arm64"
        else:
            raise RuntimeError(
                f"Unsupported architecture: {self.arch}. NVIDIA Container Toolkit only officially supports x86_64 and aarch64.")

    def _get_latest_toolkit_version(self) -> str:
        """
        Dynamically determines the latest NVIDIA Container Toolkit version available in apt.
        Falls back to DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION if unable to determine.
        """
        info("Attempting to determine latest NVIDIA Container Toolkit version from apt repositories...")
        try:
            # First, ensure apt-cache is updated to reflect latest packages
            # This 'apt update' is crucial for apt-cache madison to show current versions.
            # This 'apt update' is called after adding the repository, so it will consider the new repo.
            execute_command(["apt-get", "update"], capture_output=False)

            # apt-cache madison lists available versions. The first one is usually the latest.
            result = execute_command(
                ["apt-cache", "madison", "nvidia-container-toolkit"],
                check=True, capture_output=True, text=True
            ).stdout

            # Regex to find the version number. Matches 'toolkit | VERSION | ...'
            # Using re.DOTALL to allow '.' to match newlines if any unexpected format.
            match = re.search(
                r"nvidia-container-toolkit \| (\S+?) \|", result, re.DOTALL)
            if match:
                latest_version = match.group(1).strip()
                info(
                    f"Detected latest NVIDIA Container Toolkit version: {latest_version}")
                return latest_version
            else:
                warning(
                    "Could not parse latest NVIDIA Container Toolkit version from 'apt-cache madison' output. Falling back to default version.")
                return DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION
        except CommandExecutionError as e:
            warning(
                f"Failed to run 'apt-cache madison' to get latest version: {e}. Falling back to default version.")
            return DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION
        except Exception as e:
            warning(
                f"An unexpected error occurred while getting latest version: {e}. Falling back to default version.")
            return DEFAULT_NVIDIA_CONTAINER_TOOLKIT_VERSION

    def _check_pre_conditions(self) -> None:
        """Checks pre-conditions necessary for NVIDIA Container Toolkit installation."""
        info("Checking NVIDIA Container Toolkit pre-conditions...")

        if self.os_info.get('id') != "ubuntu":
            raise RuntimeError(
                f"Unsupported operating system: {self.os_info.get('id')}. This script is designed for Ubuntu.")

        info(f"Detected supported OS: Ubuntu ({self.os_info['codename']}).")
        info(
            f"Detected supported architecture: {self.arch} (alias: {self.arch_alias}).")

        # Check if Docker is installed and running (Critical Dependency)
        info("Verifying Docker installation and status...")
        try:
            execute_command(["docker", "info"], check=True,
                            capture_output=False, use_sudo=False)
        except (FileNotFoundError, CommandExecutionError):
            raise RuntimeError(
                "Docker is not installed or not in PATH. NVIDIA Container Toolkit explicitly depends on Docker. Please install Docker first.")

        try:
            execute_command(["systemctl", "is-active", "--quiet", "docker"],
                            check=True, capture_output=False, use_sudo=False)
        except CommandExecutionError:
            raise RuntimeError(
                "Docker service is not running. NVIDIA Container Toolkit requires Docker service to be active. Please start Docker.")
        info("Docker is installed and running.")

        # Check if NVIDIA driver is installed (Indirect Dependency - Toolkit needs drivers)
        info("Verifying NVIDIA GPU driver installation...")
        try:
            execute_command(["nvidia-smi"], check=True,
                            capture_output=False, use_sudo=False)
        except (FileNotFoundError, CommandExecutionError):
            raise RuntimeError(
                "NVIDIA GPU driver (nvidia-smi command) not found. NVIDIA Container Toolkit requires NVIDIA drivers to function. Please install NVIDIA GPU drivers first.")
        info("NVIDIA GPU driver (nvidia-smi) found.")

        info("All NVIDIA Container Toolkit pre-conditions met.")

    def _is_nvidia_toolkit_already_functional(self) -> bool:
        """Checks if NVIDIA Container Toolkit is already installed and functional."""
        info("Checking if NVIDIA Container Toolkit is already installed...")

        # Check if nvidia-container-toolkit package is installed
        try:
            execute_command(
                ["dpkg", "-s", "nvidia-container-toolkit"], check=True, capture_output=False)
            info("nvidia-container-toolkit package found.")
        except CommandExecutionError:
            info("nvidia-container-toolkit package not found.")
            return False

        # Verify if Docker is configured to use the 'nvidia' runtime
        try:
            # Use use_sudo=False for docker info as it can often be run without sudo
            # but capture_output=True to parse it.
            docker_info_output = execute_command(
                ["docker", "info", "--format", "{{.Runtimes}}"], check=True, capture_output=True, use_sudo=False).stdout
            if "nvidia" in docker_info_output:
                info("Docker is configured with 'nvidia' runtime.")
                info(
                    "NVIDIA Container Toolkit appears to be installed and configured. Skipping installation.")
                return True  # Already installed and configured
            else:
                info("NVIDIA Container Toolkit package found, but Docker runtime is not configured. Attempting to configure.")
                try:
                    # Execute nvidia-ctk with sudo by default (as per common.py's execute_command)
                    execute_command(["nvidia-ctk", "runtime", "configure",
                                    "--runtime=docker"], check=True, capture_output=False)
                    info("Docker runtime configured successfully.")
                    execute_command(
                        ["systemctl", "restart", "docker"], check=True, capture_output=False)
                    info(
                        "Docker service restarted. NVIDIA Container Toolkit now appears functional. Skipping installation.")
                    return True
                except CommandExecutionError as e:
                    warning(
                        f"Failed to configure Docker runtime or restart Docker service: {e}. Proceeding with full installation attempt.")
                    return False
        except CommandExecutionError as e:
            warning(
                f"Failed to check Docker runtime configuration: {e}. Proceeding with full installation attempt.")
            return False

    def _install_prereq_packages(self) -> None:
        """Installs necessary prerequisite packages for NVIDIA Container Toolkit."""
        # No apt update here. It will be done after adding the repo.
        info("Installing prerequisite packages (apt-transport-https, ca-certificates, curl, gnupg, lsb-release)...")
        execute_command([
            "apt-get", "install", "-y",
            "apt-transport-https", "ca-certificates", "curl", "gnupg", "lsb-release"
        ], capture_output=False)
        info("Prerequisite packages installed.")

    def _setup_nvidia_toolkit_repo_and_install(self) -> None:
        """Configures the NVIDIA Container Toolkit repository and installs packages."""
        info("Configuring production repository for NVIDIA Container Toolkit...")

        # Ensure keyrings directory exists (using pathlib for mkdir)
        Path("/usr/share/keyrings").mkdir(parents=True, exist_ok=True)

        # Determine the GPG key URL and list URL based on the chosen mirror
        gpg_key_url = f"{self.repo_base_url}/gpgkey"
        repo_list_url = f"{self.repo_base_url}/stable/deb/nvidia-container-toolkit.list"

        # Download and dearmor the GPG key
        info(f"Downloading GPG key from {gpg_key_url}...")
        curl_result = execute_command(
            ["curl", "-fsSL", gpg_key_url],
            check=True,
            capture_output=True,
            text=False,  # Raw bytes output for gpg
            use_sudo=False
        )
        execute_command(
            ["gpg", "--dearmor", "-o", NVIDIA_TOOLKIT_KEYRING],
            check=True,
            capture_output=False,
            input_data=curl_result.stdout
        )
        info(
            f"NVIDIA Container Toolkit GPG key added to {NVIDIA_TOOLKIT_KEYRING}.")

        # Add repository list
        info(f"Downloading repository list from {repo_list_url}...")
        curl_list_result = execute_command(
            ["curl", "-s", "-L", repo_list_url],
            check=True,
            capture_output=True,
            text=True,  # Read as text to apply sed-like replacement
            use_sudo=False
        )

        # Apply sed-like replacement to add signed-by and handle mirror URL
        # The original list might contain "nvidia.github.io" which needs to be replaced if using mirror.
        modified_repo_list_content = curl_list_result.stdout
        if self.mirror_region == 'cn':
            # Replace the official domain with the mirror domain in the list content
            modified_repo_list_content = modified_repo_list_content.replace(
                "nvidia.github.io", "mirrors.ustc.edu.cn/nvidia-container-toolkit"
            )
            info(
                "Replaced official repository URL with China mirror URL in the list content.")

        # Ensure the signed-by directive is added
        modified_repo_list_content = re.sub(
            r"deb https://",
            f"deb [signed-by={NVIDIA_TOOLKIT_KEYRING}] https://",
            modified_repo_list_content
        )

        # Write to file using tee
        execute_command(
            ["tee", NVIDIA_TOOLKIT_LIST],
            check=True,
            capture_output=False,
            input_data=modified_repo_list_content.encode('utf-8')
        )
        info(
            f"NVIDIA Container Toolkit stable repository added to {NVIDIA_TOOLKIT_LIST}.")

        info("Skipping optional experimental package configuration (as per standard practice).")

        # Now, update apt package list with the new repository
        # This update is critical to make 'apt-cache madison' work correctly.
        info("Updating apt package list with new repository...")
        execute_command(["apt-get", "update"], capture_output=False)
        info("Apt package list updated.")

        # Determine the version to install (this now correctly reflects packages from the added repo)
        self.toolkit_version = self._get_latest_toolkit_version()
        info(
            f"Installing NVIDIA Container Toolkit packages (version: {self.toolkit_version})...")
        execute_command([
            "apt-get", "install", "-y",
            f"nvidia-container-toolkit={self.toolkit_version}",
            f"nvidia-container-toolkit-base={self.toolkit_version}",
            f"libnvidia-container-tools={self.toolkit_version}",
            f"libnvidia-container1={self.toolkit_version}"
        ], capture_output=False)
        info("NVIDIA Container Toolkit packages installed.")

    def _configure_docker_runtime_and_restart(self) -> None:
        """Configures Docker runtime and restarts Docker service."""
        info("Configuring Docker runtime for NVIDIA Container Toolkit...")
        execute_command(["nvidia-ctk", "runtime", "configure",
                        "--runtime=docker"], capture_output=False)
        info("Docker daemon configured for NVIDIA runtime.")

        info("Restarting Docker service to apply changes...")
        execute_command(["systemctl", "restart", "docker"],
                        capture_output=False)
        info("Docker service restarted.")

    def install(self) -> int:
        """Installs NVIDIA Container Toolkit by orchestrating all steps."""
        info("Starting NVIDIA Container Toolkit installation process...")
        try:
            # Check pre-conditions before anything else
            self._check_pre_conditions()

            if self._is_nvidia_toolkit_already_functional():
                info(
                    "NVIDIA Container Toolkit is already functional. Exiting installation script successfully.")
                return 0

            self._install_prereq_packages()
            self._setup_nvidia_toolkit_repo_and_install()
            self._configure_docker_runtime_and_restart()

            info("NVIDIA Container Toolkit installation completed successfully!")
            info("You can verify the installation by running: 'docker run --rm --gpus all ubuntu nvidia-smi'")
            info("If the first run fails, it may need initialization - please try again.")
            return 0
        except (CommandExecutionError, FileNotFoundError, PermissionError, RuntimeError) as e:
            error(f"NVIDIA Container Toolkit installation failed: {e}")
            # Only print stdout/stderr if they exist for CommandExecutionError
            if isinstance(e, CommandExecutionError) and (e.stdout or e.stderr):
                error(
                    "Please review the logs above for more details on the command failure.")
            return 1
        except Exception as e:
            critical(
                f"An unexpected critical error occurred during NVIDIA Container Toolkit installation: {e}")
            return 1

    def uninstall(self) -> int:
        """Uninstalls NVIDIA Container Toolkit and associated components."""
        info("Starting NVIDIA Container Toolkit uninstallation process...")
        try:
            # Re-check pre-conditions for sudo and OS type, not other Docker/NVIDIA deps
            if self.os_info.get('id') != "ubuntu":
                raise RuntimeError(
                    f"Unsupported operating system: {self.os_info.get('id')}. This script is designed for Ubuntu.")

            info("Removing NVIDIA Container Toolkit packages...")
            try:
                execute_command([
                    "apt-get", "purge", "-y",
                    "nvidia-container-toolkit",
                    "nvidia-container-toolkit-base",
                    "libnvidia-container-tools",
                    "libnvidia-container1"
                ], check=True, capture_output=False)  # Changed to check=True for critical purge operation
                execute_command(["apt-get", "autoremove", "-y",
                                "--purge"], check=True, capture_output=False)  # Changed to check=True
                info("NVIDIA Container Toolkit-related packages removed.")
            except CommandExecutionError as e:
                warning(
                    f"Failed to remove some NVIDIA Container Toolkit packages: {e}")
                warning(
                    "Manual intervention might be needed to fully clean up packages.")

            info("Cleaning up related files and configs...")
            # Using pathlib for file operations
            keyring_path = Path(NVIDIA_TOOLKIT_KEYRING)
            list_path = Path(NVIDIA_TOOLKIT_LIST)

            if keyring_path.exists():
                try:
                    keyring_path.unlink()  # Using pathlib's unlink
                    info(
                        f"Removed NVIDIA Container Toolkit GPG key: {keyring_path}.")
                except OSError as e:  # Catch OSError for file operations
                    warning(f"Failed to remove {keyring_path}: {e}")

            if list_path.exists():
                try:
                    list_path.unlink()  # Using pathlib's unlink
                    info(
                        f"Removed NVIDIA Container Toolkit repository list: {list_path}.")
                except OSError as e:
                    warning(f"Failed to remove {list_path}: {e}")

            info("Attempting to revert Docker daemon configuration...")
            try:
                # Directly attempt to unconfigure using nvidia-ctk
                execute_command(["nvidia-ctk", "runtime", "configure",
                                "--runtime=docker", "--unconfigure"], capture_output=False)
                info("Docker runtime configuration reverted.")
            except CommandExecutionError as e:
                # Catch specific errors for old nvidia-ctk versions or other issues
                error_msg = str(e).lower()
                if "unknown flag" in error_msg or "unrecognized arguments" in error_msg or "error: unknown command" in error_msg:
                    warning(
                        "nvidia-ctk command failed, possibly due to an old version not supporting '--unconfigure'.")
                else:
                    warning(
                        f"Failed to unconfigure Docker runtime automatically: {e}")

                error(
                    "Please manually remove 'nvidia' runtime from /etc/docker/daemon.json if it exists.")
                info(
                    "Typically remove 'default-runtime': 'nvidia' and 'runtimes': { 'nvidia': { ... } } sections.")
            except FileNotFoundError:
                error(
                    "nvidia-ctk command not found. Cannot automatically revert Docker runtime configuration.")
                info(
                    "Please manually remove 'nvidia' runtime from /etc/docker/daemon.json if it exists.")
            except Exception as e:
                critical(
                    f"An unexpected error occurred while unconfiguring nvidia-ctk: {e}")
                info(
                    "Please manually remove 'nvidia' runtime from /etc/docker/daemon.json if it exists.")

            info("Restarting Docker service to finalize changes...")
            try:
                execute_command(["systemctl", "restart", "docker"],
                                check=True, capture_output=False)
                info("Docker service restarted.")
            except CommandExecutionError as e:
                error(
                    f"Failed to restart Docker service: {e}. Please check Docker status. Manual restart may be required.")

            info("NVIDIA Container Toolkit uninstallation completed.")
            return 0
        except (CommandExecutionError, FileNotFoundError, PermissionError, RuntimeError) as e:
            error(f"NVIDIA Container Toolkit uninstallation failed: {e}")
            return 1
        except Exception as e:
            critical(
                f"An unexpected critical error occurred during NVIDIA Container Toolkit uninstallation: {e}")
            return 1
