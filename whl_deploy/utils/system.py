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

import platform
import subprocess
import shutil
import re
from pathlib import Path
from typing import Dict

from whl_deploy.utils.common import info, warning, debug


class SystemInfoCollector:
    """
    Utilities for detecting host system specifications.
    Populates the DeployContext.environment directly.
    """

    @staticmethod
    def collect(ctx) -> None:
        """
        Detects system information and updates ctx.environment.
        """
        info("🔍 Collecting system information...")

        # 1. Detect Architecture
        arch = SystemInfoCollector._detect_arch()

        # 2. Detect OS (Distro & Version)
        os_raw = SystemInfoCollector._detect_os()
        os_str = f"{os_raw.get('id', 'linux')}:{os_raw.get('version_id', 'unknown')}"
        ctx.os_info = os_raw  # Store raw OS info in context

        # 3. Detect GPU Presence
        has_gpu = SystemInfoCollector._check_nvidia_gpu()
        gpu_str = "NVIDIA" if has_gpu else "None"

        # 4. Detect Docker
        docker_ver = SystemInfoCollector._detect_docker_version()

        # 5. Detect NVIDIA Toolkit (only if GPU present)
        toolkit_ver = SystemInfoCollector._detect_nvidia_toolkit(
        ) if has_gpu else "None"

        # --- Update Context Environment Directly ---
        ctx.env_arch = arch
        ctx.env_os = os_str
        ctx.env_gpu = gpu_str
        ctx.env_docker = docker_ver
        ctx.env_toolkit = toolkit_ver

        # Log findings
        info(f"   • OS      : {os_str}")
        info(f"   • Arch    : {arch}")
        info(f"   • GPU     : {gpu_str}")
        info(f"   • Docker  : {docker_ver}")
        info(f"   • Toolkit : {toolkit_ver}")

    @staticmethod
    def _detect_arch() -> str:
        arch = platform.machine().lower()
        if arch in ["amd64", "x64"]:
            return "x86_64"
        if arch in ["arm64", "aarch64_be"]:
            return "aarch64"
        return arch

    @staticmethod
    def _detect_os() -> Dict[str, str]:
        os_info = {"id": "unknown", "version_id": "unknown"}
        release_file = Path("/etc/os-release")
        if not release_file.exists():
            return os_info
        try:
            with open(release_file, "r") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        value = value.strip('"').strip("'")
                        os_info[key.lower()] = value.lower()
        except Exception:
            pass
        return os_info

    @staticmethod
    def _check_nvidia_gpu() -> bool:
        if shutil.which("nvidia-smi"):
            try:
                subprocess.run(["nvidia-smi", "-L"],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               timeout=5,
                               check=True)
                return True
            except Exception:
                return False
        elif shutil.which("jetson_release"):
            try:
                result = subprocess.run(["jetson_release"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        timeout=5)
                if "Jetson" in result.stdout:
                    return True
            except Exception:
                return False
        return False

    @staticmethod
    def _detect_docker_version() -> str:
        if shutil.which("docker") is None:
            return "None"
        try:
            result = subprocess.run(["docker", "--version"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    timeout=5)
            if result.returncode == 0:
                match = re.search(r"version\s+([0-9.]+)", result.stdout)
                return match.group(1) if match else "detected"
        except Exception:
            pass
        return "None"

    @staticmethod
    def _detect_nvidia_toolkit() -> str:
        # Check dpkg first
        try:
            result = subprocess.run([
                "dpkg-query", "--showformat=${Version}", "--show",
                "nvidia-container-toolkit"
            ],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        # Check CLI
        if shutil.which("nvidia-container-cli"):
            try:
                result = subprocess.run(["nvidia-container-cli", "--version"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True)
                match = re.search(r"version\s+([0-9.]+)", result.stdout)
                if match:
                    return match.group(1)
            except Exception:
                pass
        return "None"
