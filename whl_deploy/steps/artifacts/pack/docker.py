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
import subprocess
from pathlib import Path

from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, execute_docker_command, CommandExecutionError

class DockerImagesPackStep(DeployStep):
    """
    Packs Docker images into tar archives.
    Flow:
    1. Ensure 'raw_source' (upstream image) is available locally.
    2. Tag it as 'target' (internal system name).
    3. Save 'target' to 'source' (archive file).
    """

    def __init__(self):
        super().__init__("Pack Docker Images")

    def check_if_done(self, ctx: DeployContext) -> bool:
        # Always execute packing to ensure artifacts are up-to-date
        return False

    def run_action(self, ctx: DeployContext):
        images_config = ctx.docker_images
        if not images_config:
            info("No Docker images configured. Skipping.")
            return

        self._ensure_docker_ready()

        # Use build_tmp to store intermediate files if needed,
        # but for docker save, we usually write directly to the artifact location.

        for item in images_config:
            self._pack_single_image(ctx, item)

    def _pack_single_image(self, ctx: DeployContext, item: dict):
        raw_source = item.get("raw_source")
        target_tag = item.get("target")
        archive_rel_path = item.get("source")

        if not target_tag or not archive_rel_path:
            warning(f"Skipping invalid config item: {item}")
            return

        # The destination file path for the tar archive
        dest_file = ctx.workspace / archive_rel_path

        info(f"🐳 Processing: {target_tag}")

        try:
            # --- Phase 1: Preparation (Ensure Image Exists) ---
            # If raw_source is defined, we prioritize checking/pulling it.
            if raw_source:
                if not self._is_image_present(raw_source):
                    info(f"   ⬇️  Pulling raw source: {raw_source}")
                    execute_docker_command(["pull", raw_source], check=True)

                # Retag raw_source -> target_tag
                # This is CRITICAL: docker save exports the image with its current tags.
                # We want the archive to contain 'target_tag' so 'docker load' restores it correctly.
                if raw_source != target_tag:
                    info(f"   🏷️  Tagging {raw_source} -> {target_tag}")
                    execute_docker_command(["tag", raw_source, target_tag], check=True)

            elif not self._is_image_present(target_tag):
                # If no raw_source is given, we assume target_tag must already exist locally.
                raise RuntimeError(f"Image {target_tag} not found locally and no raw_source defined.")

            # --- Phase 2: Packing (Save to File) ---
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            info(f"   💾 Saving to {dest_file}...")

            with open(dest_file, "wb") as f:
                subprocess.run(
                    ["docker", "save", target_tag],
                    stdout=f,
                    check=True
                )

            info("   ✅ Packed successfully.")

        except Exception as e:
            raise RuntimeError(f"Failed to pack docker image {target_tag}: {e}")

    def _ensure_docker_ready(self):
        if not shutil.which("docker"):
            raise RuntimeError("Docker CLI not found on PATH.")

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
