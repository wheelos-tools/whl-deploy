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
import uuid
from pathlib import Path

from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, error
from whl_deploy.utils.file_loader import FileLoader
from whl_deploy.utils.archive_manager import ArchiveManager


class SourceCodePackStep(DeployStep):
    """
    Packs source code into artifacts.
    Strategy:
    1. If 'raw_source' exists: Fetch/Clone it -> Prepare in temp dir -> Pack to 'source'.
    2. If 'raw_source' missing: Pack existing local 'target' -> Pack to 'source'.
    """

    def __init__(self):
        super().__init__("Pack Source Code")
        self.file_loader = FileLoader()
        self.archive_manager = ArchiveManager()

    def check_if_done(self, ctx: DeployContext) -> bool:
        # Packing is a build action, usually always executed to ensure latest state.
        return False

    def run_action(self, ctx: DeployContext):
        source_items = ctx.source_codes
        if not source_items:
            info("No source code definitions found. Skipping.")
            return

        # Use a dedicated build root to avoid polluting the workspace
        build_root = ctx.workspace / "build_tmp"

        for item in source_items:
            self._pack_single_item(ctx, item, build_root)

        # Clean up build root after packing all items
        if build_root.exists():
            shutil.rmtree(build_root)

    def _pack_single_item(self, ctx: DeployContext, item: dict, build_root: Path):
        raw_source = item.get("raw_source")
        archive_rel_path = item.get("source")
        target_rel_path = item.get("target")

        if not archive_rel_path:
            warning(f"Skipping item without 'source' definition: {item}")
            return

        dest_archive = ctx.workspace / archive_rel_path

        # Prepare a temporary directory for staging the content before packing
        staging_dir = build_root / f"stage_{uuid.uuid4().hex[:8]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            source_to_pack = None

            # --- Path A: Fetch from Raw Source (CI/Clean Build Mode) ---
            if raw_source:
                info(f"📦 Packaging from raw source: {raw_source}")

                # 1. Fetch (Download/Clone) to a temp location
                fetched_path = self.file_loader.fetch(raw_source)

                # 2. Normalize content into staging_dir
                # If fetched_path is a dir (git clone), copy/move it to staging
                # If fetched_path is an archive, extract it to staging
                # if Path(fetched_path).is_dir():
                #     # We use simple copy here to detach from the temp loader location
                #     shutil.copytree(fetched_path, staging_dir, dirs_exist_ok=True)
                # else:
                self.archive_manager.decompress(Path(fetched_path), staging_dir)

                # 3. Cleanup metadata (e.g., .git) to reduce artifact size
                dot_git = staging_dir / ".git"
                if dot_git.exists():
                    shutil.rmtree(dot_git)

                source_to_pack = staging_dir

            # --- Path B: Pack from Local Target (Manual/Dev Mode) ---
            elif target_rel_path:
                local_target = ctx.project_root / target_rel_path
                if local_target.exists():
                    info(f"📦 Packaging from local target: {local_target}")
                    source_to_pack = local_target
                else:
                    raise FileNotFoundError(f"Neither 'raw_source' nor local 'target' found for {target_rel_path}")
            else:
                raise ValueError(f"Invalid config: {item}")

            # --- Final Pack Action ---
            # Ensure parent dir exists
            dest_archive.parent.mkdir(parents=True, exist_ok=True)

            info(f"   ➜ Creating artifact: {dest_archive}")
            self.archive_manager.compress(
                source_path=source_to_pack,
                output_path=dest_archive
            )
            info("   ✅ Packed successfully.")

        except Exception as e:
            raise RuntimeError(f"Failed to pack source code: {e}")
        finally:
            # Clean up staging area
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            self.file_loader.cleanup_temp_files()
