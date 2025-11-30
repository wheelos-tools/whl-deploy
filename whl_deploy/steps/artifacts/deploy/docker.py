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


import shutil
from pathlib import Path

from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, error, execute_docker_command, CommandExecutionError

class DockerImagesDeployStep(DeployStep):
    """
    Deploys Docker images to the local daemon.
    Strategy:
    1. Priority 1: Load from local 'source' archive (Offline).
    2. Priority 2: Pull from 'raw_source' (Online Fallback).
    3. Normalization: Ensure the final image is tagged as 'target'.
    """

    def __init__(self):
        super().__init__("Deploy Docker Images")

    def check_if_done(self, ctx: DeployContext) -> bool:
        # Optional: We could check if all target images exist.
        # For now, we let it run to ensure latest versions or missing tags are applied.
        return False

    def run_action(self, ctx: DeployContext):
        images_config = ctx.docker_images
        if not images_config:
            return

        self._ensure_docker_ready()

        for item in images_config:
            self._deploy_single_image(ctx, item)

    def _deploy_single_image(self, ctx: DeployContext, item: dict):
        raw_source = item.get("raw_source")
        target_tag = item.get("target")
        archive_rel_path = item.get("source")

        if not target_tag:
            warning(f"Skipping invalid item (missing target): {item}")
            return

        # Resolve absolute path to archive
        local_archive = ctx.workspace / archive_rel_path if archive_rel_path else None

        is_loaded_successfully = False
        deployment_method = ""

        try:
            # --- STRATEGY 1: Load from Archive (Offline) ---
            # If the pack step was done correctly, this archive contains the image ALREADY tagged as 'target_tag'
            if local_archive and local_archive.exists():
                info(f"📦 Found local archive: {local_archive.name}")
                info(f"   ⏳ Loading image...")
                execute_docker_command(["load", "-i", str(local_archive)], check=True)
                is_loaded_successfully = True
                deployment_method = "Archive Load"

            # --- STRATEGY 2: Online Pull (Fallback) ---
            elif raw_source:
                info(f"⚠️  Archive not found. Falling back to raw source: {raw_source}")

                # 1. Pull upstream image
                info(f"   ⬇️  Pulling {raw_source}...")
                execute_docker_command(["pull", raw_source], check=True)

                # 2. Re-Tag to match target requirement
                # This is CRITICAL for fallback mode: The system expects 'target_tag', but we pulled 'raw_source'.
                if raw_source != target_tag:
                    info(f"   🏷️  Retagging {raw_source} -> {target_tag}")
                    execute_docker_command(["tag", raw_source, target_tag], check=True)

                is_loaded_successfully = True
                deployment_method = "Online Pull"

            else:
                error(f"❌ Image {target_tag}: Neither local archive nor raw_source defined.")
                return

            # --- Verification ---
            if is_loaded_successfully:
                if self._is_image_present(target_tag):
                    info(f"   ✅ Image ready: {target_tag} (via {deployment_method})")
                else:
                    # This happens if the archive was packed with a different tag than expected
                    warning(f"   ⚠️  Image loaded, but tag '{target_tag}' is missing. The archive might contain a wrong tag.")

        except Exception as e:
            error(f"❌ Failed to deploy image {target_tag}: {e}")
            raise e

    def _ensure_docker_ready(self):
        if not shutil.which("docker"):
            raise RuntimeError("Docker not found. Please install Docker first.")
        try:
            execute_docker_command(["info"], capture_output=True, check=True)
        except CommandExecutionError:
            raise RuntimeError("Docker Daemon not reachable. Is the service running?")

    def _is_image_present(self, image_tag: str) -> bool:
        try:
            execute_docker_command(
                ["inspect", "--type=image", image_tag],
                capture_output=True,
                check=True
            )
            return True
        except CommandExecutionError:
            return False
