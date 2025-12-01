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
import shutil
import datetime
from pathlib import Path
from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning

class BundlePackStep(DeployStep):
    """
    Bundles all generated artifacts and the manifest into a single distributable file.

    Structure changes:
    - Copies manifest.yaml into artifacts/ directory first.
    - Packs the 'artifacts/' directory recursively.
    - Resulting Tar structure:
        artifacts/
          ├── manifest.yaml
          ├── docker/
          ├── data/
          └── ...
    """

    def __init__(self, output_name: str = None):
        super().__init__("Bundle Final Release")
        self.output_name = output_name

    def check_if_done(self, ctx: DeployContext) -> bool:
        return False

    def run_action(self, ctx: DeployContext):
        # 1. Define Paths
        if self.output_name:
            final_name = self.output_name
        else:
            final_name = self._generate_release_name(ctx)

        # Ensure extension is correct
        if not final_name.endswith(".tar"):
            final_name += ".tar"

        output_path = ctx.workspace / final_name
        artifacts_root = ctx.workspace / "artifacts"

        # Ensure artifacts directory exists (it should, but good for safety)
        if not artifacts_root.exists():
            artifacts_root.mkdir(parents=True, exist_ok=True)

        # 2. Copy Manifest into Artifacts Directory
        # This ensures the manifest is packed inside the 'artifacts/' folder structure
        if ctx.manifest_path and ctx.manifest_path.exists():
            dest_manifest = artifacts_root / "manifest.yaml"
            try:
                # Save manifest
                ctx.save_manifest()
                shutil.copy2(ctx.manifest_path, dest_manifest)
                info(f"   📄 Copied manifest to: {dest_manifest}")
            except Exception as e:
                warning(f"Failed to copy manifest to artifacts dir: {e}")
        else:
            warning("Manifest file not found on disk, cannot bundle it.")

        # 3. Gather files to pack
        files_to_pack = []

        # We prioritize packing the whole 'artifacts' folder
        if artifacts_root.exists() and any(artifacts_root.iterdir()):
            files_to_pack.append(artifacts_root)
        else:
            # Fallback: Scan manifest for scattered files if 'artifacts' folder is empty
            # (This is a safety net)
            warning("Artifacts directory seems empty, scanning manifest for scattered files...")
            files_to_pack.extend(self._scan_manifest_files(ctx))

        info(f"📦 Bundling final release: {output_path}")
        info("   Mode: Uncompressed Tar (Fast)")

        # 4. Create Tarball (No Compression)
        try:
            with tarfile.open(output_path, "w") as tar:
                for f_path in files_to_pack:
                    if not f_path.exists():
                        warning(f"   ⚠️ File missing, skipping: {f_path}")
                        continue

                    # arcname makes the path inside the tar relative
                    # Logic:
                    # If packing /workspace/artifacts/
                    # relative_to workspace -> "artifacts"
                    # Tar content: artifacts/manifest.yaml, artifacts/data/..., etc.
                    rel_name = f_path.relative_to(ctx.workspace)

                    info(f"   ➕ Adding directory: {rel_name}")
                    tar.add(f_path, arcname=str(rel_name))

            info(f"✅ Bundle created successfully: {output_path}")
            if output_path.exists():
                size_mb = output_path.stat().st_size / 1024 / 1024
                info(f"   Size: {size_mb:.2f} MB")

        except Exception as e:
            raise RuntimeError(f"Failed to bundle release: {e}")

    def _generate_release_name(self, ctx: DeployContext) -> str:
        """
        Generates a standardized filename based on environment context.
        Format: project_version_os_arch_hardware
        """
        # 1. Project Name (Default to 'wheelos' or get from meta)
        project = ctx.meta.get("project", "wheelos_release")

        # 2. Version (Get from meta or use Date)
        version = ctx.meta.get("version")
        if not version:
            # Fallback to date: 20231130
            version = datetime.datetime.now().strftime("%Y%m%d")

        # 3. OS (Sanitize "ubuntu:22.04" -> "ubuntu22.04")
        os_str = ctx.env_os.lower().replace(":", "").replace(" ", "")
        if os_str == "none":
            os_str = "linux"

        # 4. Architecture
        arch = ctx.env_arch
        if arch == "None":
            arch = "unknown_arch"

        # 5. Hardware (GPU/CPU)
        # Determine specific hardware tag
        if ctx.env_gpu and ctx.env_gpu != "None":
            # Could be "nvidia", "ascend", etc.
            hw = ctx.env_gpu.lower()
        else:
            hw = "cpu"

        # Construct Name
        # e.g. wheelos_release_v1.0_ubuntu22.04_x86_64_nvidia
        return f"{project}_{version}_{os_str}_{arch}_{hw}"

    def _scan_manifest_files(self, ctx: DeployContext):
        """Helper to find all local artifact paths defined in manifest."""
        paths = set()

        # Use context properties if available, otherwise fallback to manifest dict
        # This handles cases where ctx might not have parsed objects populated yet
        source_codes = getattr(ctx, 'source_codes', []) or ctx.manifest.get("artifacts", {}).get("source_codes", [])
        docker_images = getattr(ctx, 'docker_images', []) or ctx.manifest.get("artifacts", {}).get("docker_images", [])
        data_items = getattr(ctx, 'data_artifacts', []) or ctx.manifest.get("artifacts", {}).get("data", [])

        # Helper to collect paths
        def collect(items):
            for item in items:
                src = item.get("source")
                # Filter out remote URLs, we only pack local files
                if src and not src.startswith(("http:", "https:", "docker:")):
                    p = ctx.workspace / src
                    if p.exists():
                        paths.add(p)

        collect(source_codes)
        collect(docker_images)
        collect(data_items)

        # Also check maps and models from manifest dict directly
        collect(ctx.manifest.get("artifacts", {}).get("maps", []))
        collect(ctx.manifest.get("artifacts", {}).get("models", []))

        return list(paths)
