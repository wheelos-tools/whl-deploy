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

from abc import ABC, abstractmethod
import sys
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List

from whl_deploy.utils.common import info, warning, error


@dataclass
class DeployContext:
    """
    Runtime context holding configuration, environment state, and paths.
    """

    # --- Input Arguments (CLI) ---
    manifest_path: Optional[Path] = None
    bundle_path: Optional[Path] = None
    mode: str = "install"
    workspace: Path = field(default_factory=Path.cwd)

    # --- Derived Paths ---
    project_root: Path = field(init=False)

    # --- Configuration Data ---
    manifest: Dict[str, Any] = field(default_factory=dict)

    # --- System Collected Environment ---
    os_info: Dict[str, str] = field(default_factory=dict)

    # Key Sections (Synced with manifest.yaml)
    # environment keys: os, arch, gpu, docker, nvidia_toolkit
    environment: Dict[str, str] = field(default_factory=dict)
    deployment: Dict[str, str] = field(default_factory=dict)
    meta: Dict[str, str] = field(default_factory=dict)

    # --- Runtime Settings ---
    mirror_region: str = "us"

    def __post_init__(self):
        self.workspace = self.workspace.resolve()

        if self.manifest_path:
            self.manifest_path = Path(self.manifest_path).resolve()
            self._load_manifest()
            self._parse_config()
        elif not self.bundle_path:
            default_manifest = self.workspace / "manifest.yaml"
            if default_manifest.exists():
                self.manifest_path = default_manifest
                self._load_manifest()
                self._parse_config()

        if not self.environment:
            self._init_default_environment()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            error(f"Manifest file not found: {self.manifest_path}")
            sys.exit(1)
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self.manifest = yaml.safe_load(f) or {}
        except Exception as e:
            error(f"Failed to parse manifest file: {e}")
            sys.exit(1)

    def _parse_config(self):
        self.meta = self.manifest.get("meta", {})
        self.deployment = self.manifest.get("deployment", {})

        # Initialize Environment with defaults + manifest values
        raw_env = self.manifest.get("environment", {})
        self._init_default_environment(raw_env)

        self.mirror_region = self.deployment.get("mirror_region", "us")

        rel_workspace = self.deployment.get("workspace", ".")
        rel_project_root = self.deployment.get("project_root", "apollo")
        self.project_root = (self.workspace / rel_workspace /
                             rel_project_root).resolve()

        if self.mode == "install":
            info(f"📂 Target Project Root: {self.project_root}")

    def _init_default_environment(self, source: Dict[str, str] = None):
        """Ensures strict keys exist in environment dict."""
        source = source or {}
        self.environment = {
            "os": source.get("os", "None"),
            "arch": source.get("arch", "None"),
            "gpu": source.get("gpu", "None"),
            "docker": source.get("docker", "None"),
            "nvidia_toolkit": source.get("nvidia_toolkit", "None"),
        }
        # Keep extra fields
        for k, v in source.items():
            if k not in self.environment:
                self.environment[k] = v

    def reload_manifest(self, new_path: Optional[Path] = None):
        if new_path:
            self.manifest_path = new_path.resolve()
        if not self.manifest_path or not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Manifest not found at: {self.manifest_path}")
        info(f"🔄 Reloading manifest from: {self.manifest_path}")
        self._load_manifest()
        self._parse_config()

    def save_manifest(self, output_path: Optional[Path] = None) -> None:
        target_path = output_path or self.manifest_path
        if not target_path:
            error("Cannot save manifest: No output path specified.")
            return
        try:
            self.manifest["meta"] = self.meta
            self.manifest["environment"] = self.environment
            self.manifest["deployment"] = self.deployment

            with open(target_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.manifest,
                               f,
                               default_flow_style=False,
                               allow_unicode=True)
            info(f"💾 Manifest saved successfully to: {target_path}")
        except Exception as e:
            error(f"Failed to save manifest: {e}")

    # --- Simplified Accessors (Directly mapped to environment dict) ---

    @property
    def env_os(self) -> str:
        return self.environment.get("os", "None")

    @env_os.setter
    def env_os(self, value: str):
        self.environment["os"] = value

    @property
    def env_arch(self) -> str:
        return self.environment.get("arch", "None")

    @env_arch.setter
    def env_arch(self, value: str):
        self.environment["arch"] = value

    @property
    def env_arch_alias(self) -> str:
        arch_map = {
            "x86_64": "amd64",
            "aarch64": "arm64",
        }
        return arch_map.get(self.env_arch, self.env_arch)

    @property
    def env_gpu(self) -> str:
        return self.environment.get("gpu", "None")

    @env_gpu.setter
    def env_gpu(self, value: str):
        self.environment["gpu"] = value

    @property
    def env_docker(self) -> str:
        return self.environment.get("docker", "None")

    @env_docker.setter
    def env_docker(self, value: str):
        self.environment["docker"] = value

    @property
    def env_toolkit(self) -> str:
        return self.environment.get("nvidia_toolkit", "None")

    @env_toolkit.setter
    def env_toolkit(self, value: str):
        self.environment["nvidia_toolkit"] = value

    # --- Artifact Accessors ---
    @property
    def docker_images(self) -> List[Dict[str, str]]:
        return self.manifest.get("artifacts", {}).get("docker_images", [])

    @property
    def source_codes(self) -> List[Dict[str, str]]:
        return self.manifest.get("artifacts", {}).get("source_codes", [])

    @property
    def data_artifacts(self) -> List[Dict[str, Any]]:
        return self.manifest.get("artifacts", {}).get("data", [])

    @property
    def post_run_scripts(self) -> List[Dict[str, Any]]:
        return self.manifest.get("post_run", [])


class DeployStep(ABC):

    def __init__(self, name: str):
        self.name = name

    def execute(self, ctx: DeployContext):
        info(f"🔵 [Step: {self.name}] Starting...")
        try:
            if self.check_if_done(ctx):
                info(f"[Step: {self.name}] Already done. Skipping.")
                return

            self.resolve_config(ctx)
            self.prepare(ctx)
            self.run_action(ctx)

            if not self.verify(ctx):
                raise RuntimeError(f"Verification failed for {self.name}")

            self.post_process(ctx)
            info(f"[Step: {self.name}] Completed.")
        except Exception as e:
            error(f"🔴 [Step: {self.name}] Failed: {e}")
            self.rollback(ctx)
            raise e

    def resolve_config(self, ctx: DeployContext):
        """Resolve configuration (no side effects)."""
        pass

    @abstractmethod
    def check_if_done(self, ctx: DeployContext) -> bool:
        pass

    def prepare(self, ctx: DeployContext):
        pass

    @abstractmethod
    def run_action(self, ctx: DeployContext):
        pass

    def verify(self, ctx: DeployContext) -> bool:
        return True

    def post_process(self, ctx: DeployContext):
        pass

    def rollback(self, ctx: DeployContext):
        pass
