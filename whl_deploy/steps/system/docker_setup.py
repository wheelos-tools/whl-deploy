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
import getpass
from pathlib import Path

from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import (
    info,
    warning,
    execute_command,
    CommandExecutionError,
)

DOCKER_KEYRING_DIR = Path("/etc/apt/keyrings")
DOCKER_GPG_KEY_PATH = DOCKER_KEYRING_DIR / "docker.gpg"
DOCKER_REPO_LIST_PATH = Path("/etc/apt/sources.list.d/docker.list")


class DockerSetupStep(DeployStep):

    def __init__(self):
        super().__init__("Setup Docker Engine")

    def resolve_config(self, ctx: DeployContext):
        """
        Core logic: Decide which source to use based on the environment collected in Step 1.
        """
        if ctx.mirror_region == "cn":
            ctx.docker_gpg_url = (
                "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg"
            )
            repo_base = "https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu"
        else:
            ctx.docker_gpg_url = "https://download.docker.com/linux/ubuntu/gpg"
            repo_base = "https://download.docker.com/linux/ubuntu"

        # Construct apt source string
        self.repo_line = (
            f"deb [arch={ctx.env_arch_alias} signed-by={DOCKER_GPG_KEY_PATH}] "
            f"{repo_base} {ctx.os_info['version_codename']} stable\n")

    def check_if_done(self, ctx: DeployContext) -> bool:
        # 1. Check if the command exists and user in docker group
        try:
            execute_command(["docker", "info"],
                            use_sudo=True,
                            capture_output=True)
            info("Docker is running correctly.")
            groups_result = execute_command(
                ["groups", getpass.getuser()], capture_output=True)
            if "docker" in groups_result.stdout:
                info("Current user has docker group permissions.")
                return True
            else:
                warning("Current user does not have docker group permissions.")
                ctx.session['ensure_docker_group_only'] = True
                return False
        except CommandExecutionError:
            return False

    def prepare(self, ctx: DeployContext):
        if ctx.session.get('ensure_docker_group_only', False):
            # only need to ensure user permissions, skip installation
            return
        # Install prerequisite packages
        info("Installing prerequisite packages...")
        execute_command(["apt-get", "update", "-y"], use_sudo=True)
        execute_command(
            ["apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"],
            use_sudo=True,
        )
        execute_command(
            ["install", "-m", "0755", "-d",
             str(DOCKER_KEYRING_DIR)],
            use_sudo=True)

    def ensure_docker_group(self):
        user = getpass.getuser()
        if user:
            execute_command(["usermod", "-aG", "docker", user], use_sudo=True)
            info(
                f"Added user {user} to docker group. Please log out and log back in for changes to take effect."
            )
            info(
                "Alternatively, you can run 'newgrp docker' in the current session."
            )

    def run_action(self, ctx: DeployContext):
        if ctx.session.get('ensure_docker_group_only', False):
            # only need to ensure user permissions, skip installation
            self.ensure_docker_group()
            return
        # 1. Configure GPG
        info(f"Downloading GPG key from {ctx.docker_gpg_url}...")
        curl_res = execute_command(["curl", "-fsSL", ctx.docker_gpg_url],
                                   use_sudo=False,
                                   capture_output=True)
        execute_command(
            ["gpg", "--dearmor", "-o",
             str(DOCKER_GPG_KEY_PATH), "--yes"],
            use_sudo=True,
            input_data=curl_res.stdout,
        )

        # 2. Configure Repo
        info("Configuring Docker repository...")
        execute_command(
            ["tee", str(DOCKER_REPO_LIST_PATH)],
            use_sudo=True,
            input_data=self.repo_line,
        )

        # 3. Install Docker
        execute_command(["apt-get", "update", "-y"], use_sudo=True)
        info("Installing Docker packages...")
        execute_command(
            [
                "apt-get",
                "install",
                "-y",
                "docker-ce",
                "docker-ce-cli",
                "containerd.io",
                "docker-buildx-plugin",
                "docker-compose-plugin",
            ],
            use_sudo=True,
        )

        # 4. Start service
        if not os.path.exists('/.dockerenv'):
            execute_command(["systemctl", "enable", "--now", "docker"],
                            use_sudo=True)

        # 5. Configure current user permissions (optional)
        self.ensure_docker_group()
