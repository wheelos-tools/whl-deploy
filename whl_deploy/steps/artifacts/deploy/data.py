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
import shutil
import uuid
from pathlib import Path

from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, error, execute_command
from whl_deploy.utils.file_loader import FileLoader
from whl_deploy.utils.archive_manager import ArchiveManager


class GenericDataDeployStep(DeployStep):
    """
    Deploys generic data (Maps, Models, Cache).
    Strategy:
    1. Priority 1: Local Artifact (Offline).
    2. Priority 2: Raw Source (Online Fallback).
    3. Action: Extract to Temp -> Atomic Swap to Target.
    """

    def __init__(self):
        super().__init__("Deploy Generic Data")
        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()

    def check_if_done(self, ctx: DeployContext) -> bool:
        return False

    def run_action(self, ctx: DeployContext):
        # Use context helper if available, else parse manifest manually
        artifacts = ctx.data_artifacts if hasattr(ctx, "data_artifacts") else \
                    (ctx.manifest.get("artifacts", {}).get("data", []) +
                     ctx.manifest.get("artifacts", {}).get("maps", []) +
                     ctx.manifest.get("artifacts", {}).get("models", []))

        if not artifacts:
            return

        for item in artifacts:
            self._deploy_single_item(ctx, item)

    def _deploy_single_item(self, ctx: DeployContext, item: dict):
        name = item.get("name", "unnamed")
        raw_source = item.get("raw_source")
        target_rel_path = item.get("target")
        archive_rel_path = item.get("source")

        if not target_rel_path:
            warning(f"Skipping '{name}': No target defined.")
            return

        # 1. Define Paths
        final_target_dir = ctx.project_root / target_rel_path
        local_archive = ctx.workspace / archive_rel_path if archive_rel_path else None

        # 2. Prepare Temp Directory for Atomic Swap
        # Ensure parent exists
        parent_dir = final_target_dir.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        execute_command(
            ["chmod", "a+rwx", str(parent_dir)],
            use_sudo=True,
            check=True
        )

        # Create a unique temp dir on the SAME filesystem
        tmp_deploy_dir = parent_dir / f".data_tmp_{uuid.uuid4().hex[:8]}"
        tmp_deploy_dir.mkdir()

        try:
            fetched_resource = None
            source_desc = ""

            # --- STRATEGY 1: Local Artifact (Offline) ---
            if local_archive and local_archive.exists():
                info(f"📦 [{name}] Found local artifact: {local_archive.name}")
                fetched_resource = local_archive
                source_desc = "Artifact"

            # --- STRATEGY 2: Raw Source (Fallback) ---
            elif raw_source:
                info(f"⚠️  [{name}] Artifact missing. Fallback to raw source: {raw_source}")
                fetched_resource = Path(self.file_fetcher.fetch(raw_source))
                source_desc = "Raw Source"

            else:
                raise FileNotFoundError(f"[{name}] Neither 'source' artifact nor 'raw_source' available.")

            # 3. Extract / Install to Temp Directory
            info(f"   🔓 Extracting to staging area...")

            if self.archive_manager.is_archive(fetched_resource) or fetched_resource.is_dir():
                # If it's a known archive format, decompress
                self.archive_manager.decompress(fetched_resource, tmp_deploy_dir)

            else:
                # If it's a single regular file, copy it into the dir
                # (e.g., just downloading a .pb file)
                shutil.copy2(fetched_resource, tmp_deploy_dir)

            # 4. Atomic Swap
            if final_target_dir.exists():
                info(f"   ♻️  Replacing existing data at: {final_target_dir}")
                if final_target_dir.is_symlink() or final_target_dir.is_file():
                    final_target_dir.unlink()
                else:
                    # sudo privileges are required to delete the cache.
                    execute_command(
                      ["rm", "-rf", str(final_target_dir)],
                      use_sudo=True,
                      check=True)

            os.rename(tmp_deploy_dir, final_target_dir)
            info(f"   ✅ Deployed to {final_target_dir} (via {source_desc})")

        except Exception as e:
            error(f"❌ Failed to deploy '{name}': {e}")
            # Cleanup temp dir on failure
            if tmp_deploy_dir.exists():
                shutil.rmtree(tmp_deploy_dir)
            raise e
        finally:
            self.file_fetcher.cleanup_temp_files()
