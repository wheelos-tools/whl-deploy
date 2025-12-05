# Copyright 2025 The WheelOS Team. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Created Date: 2025-11-30
# Author: daohu527@gmail.com

import os
import re
from pathlib import Path
from whl_deploy.core.base import DeployStep, DeployContext

from whl_deploy.utils.common import (
    info,
    warning,
    execute_command,
    CommandExecutionError,
)

# Constant Definitions
NVIDIA_TOOLKIT_KEYRING = Path(
    "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg")
NVIDIA_TOOLKIT_LIST = Path(
    "/etc/apt/sources.list.d/nvidia-container-toolkit.list")
DEFAULT_VERSION = "1.17.8-1"


class NvidiaContainerSetupStep(DeployStep):

    def __init__(self):
        super().__init__("Setup NVIDIA Container Toolkit")
        self.toolkit_version = DEFAULT_VERSION
        self.repo_base_url = ""
        self.target_version_str = "latest"

    def check_if_done(self, ctx: DeployContext) -> bool:
        """
        Idempotency Check:
        1. If no NVIDIA GPU is detected, skip.
        2. If installed and Docker Runtime is configured, skip.
        """
        # 1. Dynamic Environment Skip (Context Aware)
        if not ctx.env_gpu == "NVIDIA":
            info("🚫 No NVIDIA GPU detected. Skipping Toolkit installation.")
            return True

        # 2. Check if package is installed
        try:
            execute_command(
                ["dpkg", "-s", "nvidia-container-toolkit"],
                check=True,
                capture_output=True,
            )
        except CommandExecutionError:
            return False  # Package not installed

        # 3. Check Docker Runtime Configuration
        try:
            docker_info = execute_command(
                ["docker", "info", "--format", "{{.Runtimes}}"],
                use_sudo=True,
                capture_output=True,
            ).stdout

            if "nvidia" in docker_info:
                info(
                    "✅ NVIDIA Container Toolkit is already installed and active."
                )
                return True
        except Exception:
            pass

        return False

    def resolve_config(self, ctx: DeployContext):
        # 1. Determine Repository URL
        if ctx.mirror_region == "cn":
            self.repo_base_url = "https://mirrors.ustc.edu.cn/libnvidia-container"
        else:
            self.repo_base_url = "https://nvidia.github.io/libnvidia-container"

        # 2. Determine Version Strategy
        self.target_version = ctx.environment.get("nvidia_toolkit", "latest")

    def prepare(self, ctx: DeployContext):
        """
        Preparation: Install dependencies -> Add Key/Repo -> apt update -> Resolve version
        """
        # 1. Install basic dependencies
        info("📦 Installing prerequisites (curl, gpg)...")
        execute_command(
            [
                "apt-get", "install", "-y", "apt-transport-https", "curl",
                "gnupg"
            ],
            use_sudo=True,
        )

        # 2. Add GPG Key
        Path("/usr/share/keyrings").mkdir(parents=True, exist_ok=True)
        gpg_url = f"{self.repo_base_url}/gpgkey"

        info(f"🔑 Fetching GPG key from {gpg_url}...")
        curl_res = execute_command(["curl", "-fsSL", gpg_url],
                                   use_sudo=False,
                                   capture_output=True,
                                   check=True)
        execute_command(
            ["gpg", "--dearmor", "-o",
             str(NVIDIA_TOOLKIT_KEYRING), "--yes"],
            use_sudo=True,
            input_data=curl_res.stdout,
        )

        # 3. Add Repo List
        repo_list_url = f"{self.repo_base_url}/stable/deb/nvidia-container-toolkit.list"
        info(f"📄 Fetching Repo list from {repo_list_url}...")

        list_content_res = execute_command(
            ["curl", "-s", "-L", repo_list_url],
            use_sudo=False,
            capture_output=True,
            text=True,
            check=True,
        )
        list_content = list_content_res.stdout

        # Replace mirror domain if in CN environment
        if ctx.mirror_region == "cn":
            list_content = list_content.replace("nvidia.github.io",
                                                "mirrors.ustc.edu.cn")

        # Inject [signed-by=...] for security
        list_content = re.sub(
            r"deb https://",
            f"deb [signed-by={NVIDIA_TOOLKIT_KEYRING}] https://",
            list_content,
        )

        execute_command(["tee", str(NVIDIA_TOOLKIT_LIST)],
                        use_sudo=True,
                        input_data=list_content)

        # 4. Update and calculate version
        info("🔄 Updating apt cache...")
        execute_command(["apt-get", "update"], use_sudo=True)

        self.toolkit_version = self._get_latest_version()

    def run_action(self, ctx: DeployContext):
        """
        Execute installation and configuration
        """
        # 1. Install Packages
        pkg_version = self.toolkit_version
        info(
            f"⬇️ Installing NVIDIA Container Toolkit version: {pkg_version}..."
        )

        # Ensure all related packages are pinned to the same version to avoid conflicts
        pkgs = [
            f"nvidia-container-toolkit={pkg_version}",
            f"nvidia-container-toolkit-base={pkg_version}",
            f"libnvidia-container-tools={pkg_version}",
            f"libnvidia-container1={pkg_version}",
        ]
        execute_command(["apt-get", "install", "-y"] + pkgs, use_sudo=True)

        # 2. Configure Docker Runtime
        info("⚙️ Configuring Docker runtime...")
        execute_command(
            ["nvidia-ctk", "runtime", "configure", "--runtime=docker"],
            use_sudo=True)

        # 3. Restart Docker
        info("🔄 Restarting Docker service...")
        if not os.path.exists('/.dockerenv'):
            execute_command(["systemctl", "restart", "docker"], use_sudo=True)

    def verify(self, ctx: DeployContext) -> bool:
        """
        Verify installation results
        """
        try:
            # Check 1: Is the runtime registered in Docker?
            res = execute_command(
                ["docker", "info", "--format", "{{.Runtimes}}"],
                use_sudo=True,
                capture_output=True,
            )
            if "nvidia" not in res.stdout:
                return False

            # Check 2: Is the CLI tool available?
            execute_command(["nvidia-ctk", "--version"],
                            capture_output=True,
                            check=True)

            return True
        except Exception:
            return False

    def _get_latest_version(self) -> str:
        """
        Helper: Get the latest available version from apt-cache
        """
        if not self.target_version and self.target_version != "latest":
            return self.target_version
        try:
            res = execute_command(
                ["apt-cache", "madison", "nvidia-container-toolkit"],
                capture_output=True,
                text=True,
            ).stdout

            # Parse output format: " package | version | repo "
            match = re.search(r"nvidia-container-toolkit \|\s+(\S+?)\s+\|",
                              res)
            if match:
                ver = match.group(1).strip()
                return ver
        except Exception as e:
            warning(
                f"⚠️ Failed to detect latest version via apt-cache, using default: {e}"
            )

        return DEFAULT_VERSION
