#!/usr/bin/env python3

import os
import platform
from pathlib import Path
from common import (
    get_os_info,
    execute_command,
    CommandExecutionError,
    info,
    warning,
    error,
    critical
)

# --- Configuration Constants ---
DOCKER_KEYRING_DIR = Path("/etc/apt/keyrings")
DOCKER_GPG_KEY_PATH = DOCKER_KEYRING_DIR / "docker.gpg"
DOCKER_REPO_LIST_PATH = Path("/etc/apt/sources.list.d/docker.list")


class DockerManager:
    """Manages Docker installation and uninstallation on Ubuntu systems."""

    def __init__(self, mirror_region: str):
        """Initializes the manager, determines OS, architecture, and mirror_region settings."""
        self.os_info = get_os_info()
        self.arch = platform.machine()
        self.arch_alias = self._get_arch_alias()
        self.mirror_region = mirror_region.lower()

    def _get_arch_alias(self) -> str:
        """Determines the Docker-compatible architecture alias."""
        arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
        alias = arch_map.get(self.arch)
        if not alias:
            raise RuntimeError(f"Unsupported architecture: {self.arch}.")
        return alias

    def _check_pre_conditions(self) -> None:
        """Checks pre-conditions necessary for Docker installation/uninstallation."""
        info("Checking pre-conditions...")
        if os.geteuid() != 0:
            raise PermissionError(
                "This script must be run with root privileges (sudo).")
        if self.os_info.get('id') != "ubuntu":
            raise RuntimeError(
                f"Unsupported OS: {self.os_info.get('id')}. This script is for Ubuntu.")
        info("All pre-conditions met.")

    def _is_docker_already_functional(self) -> bool:
        """Checks if Docker is already installed and running."""
        info("Checking if Docker is already functional...")
        try:
            # Docker commands can often be run by users in the 'docker' group without sudo
            execute_command(["docker", "info"],
                            use_sudo=False, capture_output=True)
            info("Docker daemon is responsive. Installation will be skipped.")
            return True
        except CommandExecutionError:
            info("Docker not detected or not functional. Proceeding with installation.")
            return False

    def _install_prereq_packages(self) -> None:
        """Installs necessary prerequisite packages for Docker."""
        info("Updating apt package list...")
        execute_command(["apt-get", "update", "-y"], capture_output=False)
        info("Installing prerequisite packages (ca-certificates, curl, gnupg)...")
        execute_command([
            "apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"
        ], capture_output=False)
        info("Prerequisite packages installed.")

    def _setup_docker_repo_and_install(self) -> None:
        """Sets up the Docker APT repository and installs Docker components based on the selected mirror_region."""
        if self.mirror_region == 'cn':
            gpg_url = "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg"
            repo_base_url = "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu"
        else:
            gpg_url = "https://download.docker.com/linux/ubuntu/gpg"
            repo_base_url = "https://download.docker.com/linux/ubuntu"

        info(f"Setting up Docker's GPG key from {gpg_url}...")
        execute_command(
            ["install", "-m", "0755", "-d", str(DOCKER_KEYRING_DIR)])

        curl_result = execute_command(
            ["curl", "-fsSL", gpg_url],
            use_sudo=False, text=False, check=True
        )
        execute_command(
            ["gpg", "--dearmor", "-o", str(DOCKER_GPG_KEY_PATH)],
            input_data=curl_result.stdout, check=True
        )
        execute_command(["chmod", "a+r", str(DOCKER_GPG_KEY_PATH)], check=True)
        info(f"Docker GPG key added to {DOCKER_GPG_KEY_PATH}.")

        info("Setting up Docker stable repository...")
        repo_line = (
            f"deb [arch={self.arch_alias} signed-by={DOCKER_GPG_KEY_PATH}] "
            f"{repo_base_url} {self.os_info['codename']} stable"
        )
        with open(DOCKER_REPO_LIST_PATH, 'w') as f:
            f.write(repo_line + '\n')
        info(f"Docker repository configured at {DOCKER_REPO_LIST_PATH}.")

        info("Updating apt package list with new repository...")
        execute_command(["apt-get", "update", "-y"],
                        capture_output=False, check=True)

        info("Installing Docker Engine, CLI, and plugins...")
        execute_command([
            "apt-get", "install", "-y", "docker-ce", "docker-ce-cli",
            "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"
        ], capture_output=False, check=True)
        info("Docker components installed successfully.")

    def _post_install_settings(self) -> None:
        """Applies post-installation settings for Docker."""
        info("Applying post-installation settings...")
        current_user = os.getenv('SUDO_USER')
        if current_user:
            info(f"Adding user '{current_user}' to 'docker' group...")
            execute_command(["usermod", "-aG", "docker",
                            current_user], check=True)
            info(
                f"User '{current_user}' added. Log out and log back in for changes to take effect.")
        else:
            warning(
                "SUDO_USER environment variable not set. Cannot automatically add user to 'docker' group.")
            warning(
                "To use Docker without 'sudo', add your user manually: sudo usermod -aG docker YOUR_USERNAME")

        info("Starting and enabling Docker service...")
        execute_command(["systemctl", "enable", "--now", "docker"],
                        capture_output=False, check=True)
        info("Docker service started and enabled.")

    def install(self) -> int:
        """Orchestrates the Docker installation process."""
        info("===== Starting Docker Installation =====")
        try:
            self._check_pre_conditions()
            if self._is_docker_already_functional():
                return 0

            self._install_prereq_packages()
            self._setup_docker_repo_and_install()
            self._post_install_settings()

            info("===== Docker Installation Completed Successfully! =====")
            info("To verify, run: docker run hello-world")
            return 0
        except (CommandExecutionError, FileNotFoundError, PermissionError, RuntimeError) as e:
            error(f"Docker installation failed: {e}")
            return 1
        except Exception as e:
            critical(f"An unexpected critical error occurred: {e}")
            return 1

    def uninstall(self) -> int:
        """Uninstalls Docker and cleans up associated files."""
        info("===== Starting Docker Uninstallation =====")
        try:
            self._check_pre_conditions()

            info("Stopping and disabling Docker services...")
            try:
                execute_command(["systemctl", "stop", "docker.service",
                                "docker.socket", "containerd.service"], capture_output=False)
                execute_command(["systemctl", "disable", "docker.service",
                                "docker.socket", "containerd.service"], capture_output=False)
                info("Docker services stopped and disabled.")
            except CommandExecutionError as e:
                warning(
                    f"Could not stop/disable services. This may be normal if they weren't running: {e}")

            info("Removing Docker packages...")
            try:
                execute_command([
                    "apt-get", "purge", "-y", "docker-ce", "docker-ce-cli", "containerd.io",
                    "docker-buildx-plugin", "docker-compose-plugin", "docker-ce-rootless-extras"
                ], check=True, capture_output=False)
                execute_command(["apt-get", "autoremove", "-y",
                                "--purge"], check=True, capture_output=False)
                info("Docker packages and dependencies purged.")
            except CommandExecutionError as e:
                error(
                    f"Failed to remove Docker packages. Manual cleanup may be required: {e}")
                return 1

            info("Cleaning up Docker files and directories...")
            for path in [DOCKER_GPG_KEY_PATH, DOCKER_REPO_LIST_PATH]:
                if path.exists():
                    try:
                        path.unlink()
                        info(f"Removed {path}")
                    except OSError as e:
                        warning(f"Failed to remove {path}: {e}")
                else:
                    info(f"{path} does not exist, skipping removal.")

            info("Updating apt cache after cleanup...")
            execute_command(["apt-get", "update", "-y"], capture_output=False)

            info("===== Docker Uninstallation Completed. =====")
            return 0
        except (CommandExecutionError, PermissionError, RuntimeError) as e:
            error(f"Docker uninstallation failed: {e}")
            return 1
        except Exception as e:
            critical(
                f"An unexpected critical error during uninstallation: {e}")
            return 1
