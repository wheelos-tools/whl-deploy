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
import stat
from pathlib import Path
from whl_deploy.core.base import DeployStep, DeployContext
from whl_deploy.utils.common import info, warning, error, execute_command


class PostRunStep(DeployStep):
    def __init__(self):
        super().__init__("Post-Deployment Scripts")

    def check_if_done(self, ctx: DeployContext) -> bool:
        # Post-run scripts usually imply side effects (e.g., starting services).
        # Unless there is a specific state file, we default to always running them,
        # or rely on the scripts themselves to handle idempotency.
        return False

    def run_action(self, ctx: DeployContext):
        # 1. Retrieve script configuration from manifest
        scripts_config = ctx.manifest.get("post_run", [])
        if not scripts_config:
            info("No post-run scripts defined.")
            return

        # 2. Determine the root directory of the deployed source code (Base Path)
        # We assume scripts are located within the source directory we just deployed.
        base_path = ctx.project_root
        info(f"📂 Resolving scripts relative to: {base_path}")

        # 3. Execute scripts sequentially
        for item in scripts_config:
            self._execute_single_script(base_path, item)

    def _execute_single_script(self, base_path: Path, config: dict):
        script_rel_path = config.get("script")
        name = config.get("name", script_rel_path)
        args = config.get("args", [])
        use_sudo = config.get("sudo", False)
        interpreter = config.get("interpreter")  # e.g., "python3", "bash"

        if not script_rel_path:
            return

        # Construct full path
        script_full_path = base_path / script_rel_path

        if not script_full_path.exists():
            raise FileNotFoundError(f"❌ Post-run script not found: {script_full_path}")

        info(f"🚀 Running [{name}]: {script_full_path} {' '.join(args)}")

        # Ensure script has execution permissions (if running directly without interpreter)
        if not interpreter:
            try:
                current_mode = script_full_path.stat().st_mode
                # Add +x permission (User, Group, Other)
                script_full_path.chmod(
                    current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
            except PermissionError:
                warning(
                    f"⚠️ Could not change permissions for {script_full_path}. Attempting to run anyway."
                )

        # Construct Command
        cmd = []
        if interpreter:
            cmd.append(interpreter)

        cmd.append(str(script_full_path))
        cmd.extend(args)

        # Execute
        # Setting cwd=base_path is critical as many scripts assume they run from project root
        try:
            execute_command(cmd, use_sudo=use_sudo, cwd=str(base_path), check=True)
            info(f"✅ [{name}] finished successfully.")
        except Exception as e:
            error(f"❌ [{name}] failed: {e}")
            raise e
