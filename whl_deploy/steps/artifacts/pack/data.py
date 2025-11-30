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


class GenericDataPackStep(DeployStep):
    """
    Packs generic data (Maps, Models, etc.).
    Flow:
    1. If raw_source exists: Fetch -> Extract to Staging -> Pack Staging to source.
    2. If raw_source missing: Pack existing local Target -> Pack to source.
    """

    def __init__(self):
        super().__init__("Pack Generic Data")
        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()

    def check_if_done(self, ctx: DeployContext) -> bool:
        return False

    def run_action(self, ctx: DeployContext):
        # Aggregate all data-like artifacts
        artifacts = ctx.data_artifacts
        # Fallback if context helper not defined:
        if not hasattr(ctx, "data_artifacts"):
             artifacts = ctx.manifest.get("artifacts", {}).get("data", [])

        if not artifacts:
            info("No data artifacts configured. Skipping.")
            return

        build_root = ctx.workspace / "build_tmp"

        for item in artifacts:
            self._pack_single_item(ctx, item, build_root)

        # Cleanup build root
        if build_root.exists():
            shutil.rmtree(build_root)

    def _pack_single_item(self, ctx: DeployContext, item: dict, build_root: Path):
        name = item.get("name", "unnamed")
        raw_source = item.get("raw_source")
        target_rel_path = item.get("target")
        archive_rel_path = item.get("source")

        if not archive_rel_path:
            warning(f"Skipping '{name}': Missing 'source' definition.")
            return

        dest_archive = ctx.workspace / archive_rel_path

        # Create a clean staging directory for this item
        staging_dir = build_root / f"stage_{uuid.uuid4().hex[:8]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        info(f"📦 Processing '{name}'...")

        try:
            source_to_pack = None

            # --- STRATEGY 1: Pack from Raw Source (Clean Build) ---
            if raw_source:
                info(f"   Fetching raw source: {raw_source}")
                fetched_path = Path(self.file_fetcher.fetch(raw_source))

                # Prepare content in staging_dir
                # Assume archive, extract to staging
                # If raw source is a single file (not archive), ArchiveManager should handle or we check extension
                # Here we assume it's an archive based on context.
                # Refinement: If fetcher returns a non-archive file, just copy it.
                if self.archive_manager.is_archive(fetched_path) or fetched_path.is_dir():
                    self.archive_manager.decompress(fetched_path, staging_dir)
                else:
                    # It's a single file (e.g. model.pb), copy it directly
                    shutil.copy2(fetched_path, staging_dir)

                source_to_pack = staging_dir

            # --- STRATEGY 2: Pack from Local Target (Snapshot) ---
            elif target_rel_path:
                local_target = ctx.project_root / target_rel_path
                if local_target.exists():
                    info(f"   Snapshotting local target: {local_target}")
                    source_to_pack = local_target
                else:
                    raise FileNotFoundError(f"[{name}] Target {local_target} not found and no raw_source defined.")
            else:
                warning(f"Skipping '{name}': No raw_source and no target defined.")
                return

            # --- Final Pack ---
            dest_archive.parent.mkdir(parents=True, exist_ok=True)
            info(f"   Packing to: {dest_archive}")

            self.archive_manager.compress(
                source_path=source_to_pack,
                output_path=dest_archive
            )
            info("   ✅ Packed successfully.")

        except Exception as e:
            raise RuntimeError(f"Failed to pack '{name}': {e}")
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            self.file_fetcher.cleanup_temp_files()
