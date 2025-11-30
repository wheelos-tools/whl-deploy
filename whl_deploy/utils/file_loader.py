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
import tempfile
import urllib.request
import subprocess
import cgi
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError
from typing import List, Optional, Union


from whl_deploy.utils.common import (
    info,
    warning,
    execute_docker_command,
    CommandExecutionError,
)


class FileFetcherError(Exception):
    """Custom exception for errors during file fetching/cloning."""

    pass


class FileLoader:
    """
    A utility to fetch files or repositories from various sources (Local, HTTP/HTTPS, Git, Docker).
    Handles temporary directory creation and cleanup automatically for downloaded artifacts.
    """

    def __init__(self):
        # Stores only temporary directories created by this instance.
        self.temp_dirs: List[Path] = []

    def fetch(
        self, source_path: str, destination_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """
        Fetches a resource from a given source.

        Args:
            source_path: The URL (http, https), Git URI, Docker URI (docker://), or local path.
            destination_dir: Optional directory.
                             - For files: Download destination folder.
                             - For Git: Parent folder for the clone.
                             - If None: A temporary directory is created.

        Returns:
            Path: The absolute path to the local file or cloned repository.
        """
        # Convert destination_dir to Path object if provided
        dest_path = Path(destination_dir).resolve() if destination_dir else None

        # 1. Git Repository Detection
        if (
            source_path.endswith(".git")
            or source_path.startswith("git@")
            or source_path.startswith("ssh://")
            or "/git/" in source_path
        ):
            info(f"📡 Detected Git repository: {source_path}")
            return self._git_clone(source_path, dest_path)

        # 2. Docker Image Detection (docker://image:tag)
        elif source_path.startswith("docker://"):
            info(f"🐳 Detected Docker URI: {source_path}")
            return self._download_docker_image(source_path, dest_path)

        # 3. HTTP/HTTPS/FTP URL Detection
        elif source_path.startswith(("http://", "https://", "ftp://")):
            info(f"🌐 Detected URL resource: {source_path}")
            return self._download_file(source_path, dest_path)

        # 4. Local Path
        else:
            local_path = Path(source_path).resolve()
            info(f"📂 Using local path: {local_path}")
            if not local_path.exists():
                raise FileFetcherError(f"Local path not found: {local_path}")
            return local_path

    def _download_file(self, url: str, destination_dir: Optional[Path]) -> Path:
        """Helper to download a file from a URL with progress bar."""
        if destination_dir is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="file_fetcher_"))
            self.temp_dirs.append(temp_dir)
            destination_dir = temp_dir
        else:
            destination_dir.mkdir(parents=True, exist_ok=True)

        info(f"⬇️  Downloading from {url}...")

        try:
            with urllib.request.urlopen(url) as response:
                # Determine Filename
                content_disposition = response.info().get("Content-Disposition")
                filename = None
                if content_disposition:
                    _, params = cgi.parse_header(content_disposition)
                    filename = params.get("filename")

                if not filename:
                    filename = Path(urlparse(url).path).name
                if not filename:
                    filename = "downloaded_artifact"

                local_filepath = destination_dir / filename

                # Progress Bar
                total_size = int(response.info().get("Content-Length", 0))
                block_size = 8192

                with open(local_filepath, "wb") as out_file:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        out_file.write(buffer)

                info(f"✅ Download completed: {local_filepath}")
                return local_filepath

        except (URLError, HTTPError) as e:
            raise FileFetcherError(f"Network error while downloading '{url}': {e}")
        except Exception as e:
            raise FileFetcherError(f"Unexpected error during download: {e}")

    def _git_clone(self, repo_url: str, destination_dir: Optional[Path]) -> Path:
        """Helper to clone a Git repository."""
        if destination_dir is None:
            clone_parent_dir = Path(tempfile.mkdtemp(prefix="git_clone_"))
            self.temp_dirs.append(clone_parent_dir)
        else:
            clone_parent_dir = destination_dir
            clone_parent_dir.mkdir(parents=True, exist_ok=True)

        repo_name = Path(repo_url.rstrip("/").split("/")[-1]).stem
        final_repo_path = clone_parent_dir / repo_name

        if final_repo_path.exists():
            if destination_dir is None:
                warning(f"Cleaning existing temp git directory: {final_repo_path}")
                shutil.rmtree(final_repo_path)
            else:
                warning(
                    f"Target git directory '{final_repo_path}' already exists. Skipping clone."
                )
                return final_repo_path

        info(f"🐑 Cloning '{repo_url}' into '{final_repo_path}'...")

        try:
            command = ["git", "clone", "--depth", "1", repo_url, str(final_repo_path)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            info(f"✅ Repository cloned successfully.")
            return final_repo_path

        except FileNotFoundError:
            raise FileFetcherError("Git command not found. Please install Git.")
        except subprocess.CalledProcessError as e:
            raise FileFetcherError(f"Git clone failed: {e.stderr.strip()}")
        except Exception as e:
            raise FileFetcherError(f"Git clone error: {e}")

    def _download_docker_image(
        self, docker_uri: str, destination_dir: Optional[Path]
    ) -> Path:
        """
        Helper to pull a Docker image and save it as a .tar file.
        Useful for packing scenarios.
        """
        image_tag = docker_uri.replace("docker://", "")

        if destination_dir is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="docker_img_"))
            self.temp_dirs.append(temp_dir)
            destination_dir = temp_dir
        else:
            destination_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename (replace / and : with _)
        filename = f"{image_tag.replace('/', '_').replace(':', '_')}.tar"
        output_path = destination_dir / filename

        info(f"⚓ Pulling docker image '{image_tag}'...")
        try:
            # 1. Pull
            execute_docker_command(["pull", image_tag], check=True)

            # 2. Save to tar
            info(f"💾 Saving image to '{output_path}'...")
            execute_docker_command(
                ["save", "-o", str(output_path), image_tag], check=True
            )

            return output_path

        except CommandExecutionError as e:
            raise FileFetcherError(
                f"Failed to pull/save docker image '{image_tag}': {e.stderr or e}"
            )

    def cleanup_temp_files(self) -> None:
        """Removes any temporary directories created during this session."""
        if not self.temp_dirs:
            return

        info(f"🧹 Cleaning up {len(self.temp_dirs)} temporary location(s)...")
        for temp_dir in self.temp_dirs:
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except OSError as e:
                    warning(f"Failed to remove temp dir '{temp_dir}': {e}")
        self.temp_dirs.clear()
