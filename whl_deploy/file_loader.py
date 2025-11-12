from tqdm import tqdm
import shutil
import urllib.request
from urllib.error import URLError, HTTPError
import subprocess
import tempfile
from typing import List, Optional, Union
from urllib.parse import urlparse
from pathlib import Path

from whl_deploy.common import info, error, warning, critical

# --- Custom Exceptions ---


class FileFetcherError(Exception):
    """Custom exception for errors during file fetching/cloning."""

    pass


class FileLoader:
    def __init__(self, logger_instance=None):
        # Stores only temporary directories created by FileLoader.
        # Files downloaded into these directories will be cleaned up automatically.
        self.temp_dirs: List[Path] = []

    def fetch(
        self, source_path: str, destination_dir: Optional[Union[str, Path]] = None
    ) -> Path:
        """
        Fetches a resource from a given source (local path, URL, or Git repository).

        Args:
            source_path: The URL, local path, or Git repository URL.
            destination_dir: Optional directory to place the fetched resource.
                             - For files: downloads to this directory.
                             - For Git repos: clones into a subdirectory within this directory.
                               If None, a temporary directory will be created.

        Returns:
            The local path (as a Path object) to the fetched resource.
            - For local files/URLs: The path to the file.
            - For Git repos: The path to the cloned repository directory.

        Raises:
            FileFetcherError: If fetching/cloning fails.
        """
        # Convert destination_dir to Path object if provided
        if destination_dir is not None:
            destination_dir = Path(destination_dir).resolve()

        if source_path.startswith(("http://", "https://", "ftp://")):
            # Heuristic for Git repositories:
            # Check for common Git hosting domains or typical Git URL patterns.
            # This is a best-effort check. A robust solution might involve `git ls-remote`.
            # For this context, it's acceptable.
            if source_path.endswith(".git") or "/git/" in source_path:
                info(f"Attempting to clone HTTPS/HTTP Git repository: {source_path}")
                return self._git_clone(source_path, destination_dir)
            else:
                info(f"Downloading file from URL: {source_path}")
                return self._download_file(source_path, destination_dir)
        elif source_path.startswith("git@"):  # SSH Git protocol
            info(f"Attempting to clone SSH Git repository: {source_path}")
            return self._git_clone(source_path, destination_dir)
        else:  # Assume local file or directory
            # Resolve to absolute path
            local_path = Path(source_path).resolve()
            info(f"Using local path: {local_path}")
            if not local_path.exists():
                raise FileFetcherError(f"Local path not found: {local_path}")
            return local_path

    def _download_file(self, url: str, destination_dir: Optional[Path]) -> Path:
        """Helper to download a file from a URL."""
        if destination_dir is None:
            # Create a temporary directory for the downloaded file
            temp_dir = Path(tempfile.mkdtemp(prefix="file_fetcher_"))
            self.temp_dirs.append(temp_dir)  # Track the temp dir for cleanup
            destination_dir = temp_dir
        else:
            # Ensure it's a Path object
            destination_dir.mkdir(parents=True, exist_ok=True)

        # Parse URL to get a cleaner filename (removing query params etc.)
        parsed_url = urlparse(url)
        # Use filename from path or default to 'downloaded_file' if not available
        suggested_filename = Path(parsed_url.path).name or "downloaded_file"
        local_filename = (
            destination_dir / suggested_filename
        )  # Use Path for concatenation

        info(f"Attempting to download '{url}' to '{local_filename}'...")
        try:
            with urllib.request.urlopen(url) as response:
                # Get the total file size, if available (from Content-Length header)
                total_size = response.length
                block_size = 8192  # 8 KB chunks
                # Create a progress bar using tqdm
                # If total_size is available, tqdm will show a percentage and ETA.
                # If total_size is not available (e.g., some servers don't provide Content-Length),
                # tqdm will display a non-deterministic progress bar.
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=str(local_filename),
                    miniters=1,
                ) as pbar:
                    with open(local_filename, "wb") as out_file:
                        while True:
                            buffer = response.read(block_size)
                            # Break if no more data is read (end of file)
                            if not buffer:
                                break
                            out_file.write(buffer)
                            pbar.update(len(buffer))
                return local_filename
        except (URLError, HTTPError) as e:
            raise FileFetcherError(f"Failed to download file from '{url}': {e}")
        except Exception as e:
            raise FileFetcherError(f"An unexpected error occurred during download: {e}")

    def _git_clone(self, repo_url: str, destination_dir: Optional[Path]) -> Path:
        """Helper to clone a Git repository."""
        # If no specific destination_dir is given, clone into a temporary directory
        if destination_dir is None:
            clone_parent_dir = Path(tempfile.mkdtemp(prefix="git_clone_"))
            # Track the temp dir for cleanup
            self.temp_dirs.append(clone_parent_dir)
        else:
            clone_parent_dir = destination_dir  # Already a Path object
            clone_parent_dir.mkdir(parents=True, exist_ok=True)
            info(f"Cloning repository into '{clone_parent_dir}'...")

        # Git clone creates a subdirectory named after the repo.
        # Extract repo name from URL to determine the final path.
        # This is a heuristic and might need refinement for complex URLs or non-standard repo names.
        # Get last part, remove extension if any
        repo_name = Path(repo_url.split("/")[-1]).stem
        cloned_repo_path = clone_parent_dir / repo_name

        # Handle existing target directory for clone
        if cloned_repo_path.exists():
            if (
                destination_dir is None
            ):  # If we created a temporary directory, always ensure it's clean
                warning(
                    f"Temporary clone directory '{cloned_repo_path}' already exists. Deleting and re-cloning to ensure freshness."
                )
                try:
                    shutil.rmtree(cloned_repo_path)
                except OSError as e:
                    raise FileFetcherError(
                        f"Failed to clean up existing temporary clone directory '{cloned_repo_path}': {e}"
                    )
            else:  # If user provided destination_dir, warn and return existing path
                warning(
                    f"Target clone directory '{cloned_repo_path}' already exists. "
                    "Skipping clone to avoid overwriting. If you want to re-clone, delete it first or use a new destination."
                )
                return cloned_repo_path

        try:
            # Use 'git clone --depth 1' for shallow clone if only latest version is needed, faster.
            # Use full clone 'git clone' if history is required.
            # For typical AD data setup, shallow clone is often sufficient.
            command = ["git", "clone", "--depth", "1", repo_url, str(cloned_repo_path)]
            info(f"Executing Git clone: {' '.join(command)}")

            # Capture output for better error messages
            process = subprocess.run(
                command, check=True, capture_output=True, text=True
            )
            info(f"Successfully cloned '{repo_url}' to '{cloned_repo_path}'")
            return cloned_repo_path
        except FileNotFoundError:
            raise FileFetcherError(
                "Git command not found. Please ensure Git is installed and in your PATH."
            )
        except subprocess.CalledProcessError as e:
            raise FileFetcherError(
                f"Git clone failed for '{repo_url}' with exit code {e.returncode}. "
                "Ensure repository exists, you have access, and SSH keys/credentials are set up.\n"
                f"STDOUT: {e.stdout.strip()}\nSTDERR: {e.stderr.strip()}"
            )
        except Exception as e:
            raise FileFetcherError(
                f"An unexpected error occurred during Git clone: {e}"
            )

    def cleanup_temp_files(self) -> None:
        """Removes any temporary directories created during fetching."""
        for temp_dir in self.temp_dirs:
            if temp_dir.exists():
                try:
                    if temp_dir.is_dir():
                        info(f"Cleaning up temporary directory: {temp_dir}")
                        shutil.rmtree(temp_dir)
                    # No need to handle files separately as we only track temp_dirs
                except OSError as e:
                    warning(f"Failed to remove temporary path '{temp_dir}': {e}")
        self.temp_dirs.clear()
