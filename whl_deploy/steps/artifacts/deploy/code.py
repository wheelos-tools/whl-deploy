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
from whl_deploy.utils.common import info, warning, error
from whl_deploy.utils.file_loader import FileLoader
from whl_deploy.utils.archive_manager import ArchiveManager


class SourceCodeDeployStep(DeployStep):
    """
    Deploys source code to the target directory.
    Strategy:
    1. Priority 1: Install from local 'source' artifact (Offline).
    2. Priority 2: Fetch from 'raw_source' (Online Fallback).
    3. Action: Extract to temp dir -> Atomic Swap to 'target'.
    """

    def __init__(self):
        super().__init__("Deploy Source Code")
        self.file_loader = FileLoader()
        self.archive_manager = ArchiveManager()

    def check_if_done(self, ctx: DeployContext) -> bool:
        # Deployment usually requires forcing state or checking version files.
        # For simplicity, we return False to ensure "apply" logic runs.
        return False

    def run_action(self, ctx: DeployContext):
        source_items = ctx.source_codes
        if not source_items:
            info("No source code definitions found. Skipping.")
            return

        for item in source_items:
            self._deploy_single_item(ctx, item)

    def _deploy_single_item(self, ctx: DeployContext, item: dict):
        raw_source = item.get("raw_source")
        archive_rel_path = item.get("source")
        target_rel_path = item.get("target")

        if not target_rel_path:
            error(f"Skipping invalid item (missing target): {item}")
            return

        # 1. Define Paths
        final_target_dir = ctx.project_root / target_rel_path
        local_archive = ctx.workspace / archive_rel_path if archive_rel_path else None

        # 2. Prepare Temporary Directory (Atomic Strategy)
        # Create temp dir on the same filesystem as target to ensure atomic rename
        parent_dir = final_target_dir.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        # Use a unique name to avoid collisions during parallel runs or leftovers
        tmp_deploy_dir = parent_dir / f".deploy_tmp_{uuid.uuid4().hex[:8]}"
        tmp_deploy_dir.mkdir()

        deploy_source_desc = ""

        try:
            fetched_resource = None

            # --- STRATEGY 1: Local Artifact (Offline) ---
            if local_archive and local_archive.exists():
                deploy_source_desc = f"Artifact ({local_archive.name})"
                info(f"📦 Deploying from local artifact: {local_archive}")
                fetched_resource = local_archive

            # --- STRATEGY 2: Raw Source (Fallback) ---
            elif raw_source:
                deploy_source_desc = f"Raw Source ({raw_source})"
                info(f"⚠️  Local artifact not found. Falling back to raw source: {raw_source}")
                # FileLoader handles Git cloning or File downloading
                fetched_resource = self.file_loader.fetch(raw_source)

            else:
                raise FileNotFoundError(
                    f"Neither local artifact '{archive_rel_path}' nor 'raw_source' is available."
                )

            # 3. Populate Temporary Directory
            info(f"   🔓 Extracting/Copying to staging area...")

            # If fetched resource is a directory (e.g., git clone result), copy it.
            # If it's an archive, decompress it.
            resource_path = Path(fetched_resource)
            self.archive_manager.decompress(resource_path, tmp_deploy_dir)

            # 4. Atomic Swap
            if final_target_dir.exists():
                info(f"   🔄 Replacing existing target: {final_target_dir}")
                if final_target_dir.is_symlink() or final_target_dir.is_file():
                    final_target_dir.unlink()
                else:
                    shutil.rmtree(final_target_dir)

            os.rename(tmp_deploy_dir, final_target_dir)
            info(f"   ✅ Successfully deployed via {deploy_source_desc}")

        except Exception as e:
            error(f"❌ Failed to deploy to {target_rel_path}: {e}")
            # Cleanup temp dir on failure
            if tmp_deploy_dir.exists():
                shutil.rmtree(tmp_deploy_dir)
            raise e
        finally:
            self.file_loader.cleanup_temp_files()
