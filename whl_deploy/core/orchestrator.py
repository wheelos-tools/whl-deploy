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


from whl_deploy.core.base import DeployContext
from whl_deploy.steps.system.docker_setup import DockerSetupStep
from whl_deploy.steps.system.nvidia_container_setup import NvidiaContainerSetupStep
from whl_deploy.steps.artifacts.deploy.code import SourceCodeDeployStep
from whl_deploy.steps.artifacts.deploy.data import GenericDataDeployStep
from whl_deploy.steps.artifacts.deploy.docker import DockerImagesDeployStep
from whl_deploy.steps.artifacts.deploy.bundle import BundleUnpackStep
from whl_deploy.steps.artifacts.pack.code import SourceCodePackStep
from whl_deploy.steps.artifacts.pack.data import GenericDataPackStep
from whl_deploy.steps.artifacts.pack.docker import DockerImagesPackStep
from whl_deploy.steps.artifacts.pack.bundle import BundlePackStep
from whl_deploy.steps.execution.scripts import PostRunStep


class Orchestrator:
    def __init__(self, ctx: DeployContext):
        self.ctx = ctx

    def run(self):
        if self.ctx.mode == "pack":
            self._run_pack_pipeline()
        elif self.ctx.mode == "install":
            self._run_install_pipeline()
        else:
            raise ValueError(f"Unknown mode: {self.ctx.mode}")

    def _run_install_pipeline(self):
        """
        Installation Pipeline: Strictly follows Env -> Prepare -> Source -> Data -> Post order.
        """
        pipeline = [
            BundleUnpackStep(),
            # --- Phase 2: System Preparation ---
            DockerSetupStep(),
            NvidiaContainerSetupStep(),
            # --- Phase 3: Core Artifacts Deployment ---
            SourceCodeDeployStep(),
            # Data Deployment: Depends on directory established by Source.
            GenericDataDeployStep(),  # Map, Model, Cache
            # Image Import: Relatively independent.
            DockerImagesDeployStep(),
            # --- Phase 4: Execution (Post-Run) ---
            # Depends on script files in Source.
            PostRunStep(),
        ]

        print(f"\n 🚀 Starting Install Pipeline in {self.ctx.workspace}...")
        for step in pipeline:
            step.execute(self.ctx)

    def _run_pack_pipeline(self):
        """
        Packing Pipeline
        """
        pipeline = [
            SourceCodePackStep(),
            GenericDataPackStep(),
            DockerImagesPackStep(),
            BundlePackStep(),
        ]

        print(f"\n 📦 Starting Pack Pipeline...")
        for step in pipeline:
            step.execute(self.ctx)
