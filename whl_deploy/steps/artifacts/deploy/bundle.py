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


import tarfile
from pathlib import Path
from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, error


class BundleUnpackStep(DeployStep):
    """
    Bootstrap Step:
    Checks if a deployment bundle (.tar) is provided.
    If so, extracts it to the workspace and initializes the manifest.
    """

    def __init__(self):
        super().__init__("Unpack Deployment Bundle")

    def check_if_done(self, ctx: DeployContext) -> bool:
        if not ctx.bundle_path:
            # No bundle provided, assume folder mode
            return True
        return False

    def run_action(self, ctx: DeployContext):
        if not ctx.bundle_path:
            info("No bundle path provided. Assuming standard directory-based deployment.")
            return

        bundle_file = Path(ctx.bundle_path).resolve()
        if not bundle_file.exists():
            raise FileNotFoundError(f"Bundle file not found: {bundle_file}")

        info(f"📦 Found deployment bundle: {bundle_file}")
        info(f"   📂 Extracting to workspace: {ctx.workspace} ...")

        try:
            # 1. Extract Tarball
            with tarfile.open(bundle_file, "r") as tar:
                def safe_members(members):
                    for member in members:
                        if member.name.startswith("/") or ".." in member.name:
                            warning(f"⚠️  Skipping suspicious file path: {member.name}")
                            continue
                        yield member

                tar.extractall(path=ctx.workspace, members=safe_members(tar))

            info("✅ Bundle extracted successfully.")

            # 2. Locate Manifest
            # Priority 1: inside artifacts/ (New structure)
            # Priority 2: at root (Legacy structure)

            artifacts_manifest = ctx.workspace / "artifacts" / "manifest.yaml"
            target_manifest = None

            if artifacts_manifest.exists():
                target_manifest = artifacts_manifest
                info(f"   🔍 Found manifest in artifacts directory.")
            else:
                # Not found anywhere
                raise FileNotFoundError(
                    f"Bundle extracted, but 'manifest.yaml' not found in "
                    f"{ctx.workspace}/artifacts or {ctx.workspace}"
                )

            # 3. Reload context directly pointing to the file location
            info(f"   📄 Loading manifest: {target_manifest}")
            ctx.reload_manifest(target_manifest)

        except Exception as e:
            raise RuntimeError(f"Failed to unpack bundle: {e}")
