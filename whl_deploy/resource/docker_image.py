#!/usr/bin/env python3

from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from whl_deploy.common import (
    execute_docker_command,
    CommandExecutionError,
    info, warning, error, critical
)

from whl_deploy.file_loader import FileLoader, FileFetcherError

# --- Configuration Constants ---
DEFAULT_IMAGE_SAVE_FILENAME = "whl_docker_image.tar"
# Changed TEMP_DOWNLOAD_DIR strategy. FileLoader should manage its own temp files.
# If a shared temp directory is absolutely needed, use tempfile module for robustness.


class DockerImageError(Exception):
    """Custom exception for errors during Docker image operations."""
    pass

# --- DockerImageManager Implementation ---


class DockerImageManager:
    def __init__(self):
        # FileLoader should handle its own temporary file management.
        # No need to pre-define TEMP_DOWNLOAD_DIR here, unless FileLoader requires it.
        self.file_fetcher = FileLoader()
        info("Initialized DockerImageManager.")

    def _check_docker_daemon_status(self) -> None:
        """Checks if Docker daemon is running."""
        info("Checking Docker daemon status...")
        try:
            # Using `docker info` is robust for checking daemon connectivity.
            # `check=True` ensures an exception is raised on non-zero exit code.
            # `use_sudo=True` is generally safer for Docker commands if the user is not in the docker group.
            # However, `docker info` usually doesn't require sudo if the user is correctly configured for Docker.
            # If `execute_docker_command` defaults to sudo, then no need to specify it.
            execute_docker_command(["info"], capture_output=True, check=True)
            info("Docker daemon is active.")
        except CommandExecutionError as e:
            # Check stderr for specific error messages for clearer diagnostics
            stderr_output = e.stderr.lower() if e.stderr else ""
            if "cannot connect to the docker daemon" in stderr_output:
                raise DockerImageError(
                    f"Docker daemon is not running or accessible. Please start Docker service. "
                    f"Error details: {e.stderr.strip()}" if e.stderr else "No detailed error message."
                )
            else:
                raise DockerImageError(
                    f"Failed to check Docker daemon status due to unexpected error: {e.stderr.strip()}" if e.stderr else str(
                        e)
                )
        except FileNotFoundError:
            raise DockerImageError(
                "Docker command not found. Please ensure Docker is installed and in your PATH."
            )
        except Exception as e:
            raise DockerImageError(
                f"An unexpected error occurred while checking Docker daemon status: {e}"
            )

    def _get_image_id(self, image_name_or_id: str) -> Optional[str]:
        """
        Attempts to get the full image ID for a given image name or ID.
        Returns None if the image is not found.
        """
        try:
            # Use docker inspect for a robust check
            result = execute_docker_command(
                ["inspect", "--format", "{{.Id}}", image_name_or_id],
                capture_output=True,
                text=True,
                check=True  # `check=True` will cause CommandExecutionError if image not found
            )
            return result.stdout.strip()
        except CommandExecutionError as e:
            # `docker inspect` with `check=True` will raise CommandExecutionError if image not found.
            # Check stderr to confirm it's a "no such image" error rather than a genuine inspect error.
            if "No such image" in (e.stderr or ""):
                return None
            else:
                # Log unexpected errors during inspect but don't re-raise for image presence check
                warning(
                    f"Error inspecting image '{image_name_or_id}': {e.stderr.strip()}" if e.stderr else str(
                        e)
                )
                return None
        except Exception as e:
            warning(
                f"An unexpected error occurred while inspecting image '{image_name_or_id}': {e}")
            return None

    def _is_image_present(self, image_name: str) -> bool:
        """Checks if a Docker image with the given name is already present locally."""
        info(f"Checking if image '{image_name}' is present locally...")
        image_id = self._get_image_id(image_name)
        if image_id:
            info(f"Image '{image_name}' (ID: {image_id}) is present.")
            return True
        else:
            info(f"Image '{image_name}' is not present.")
            return False

    def save_images(self, image_names: List[str], output_filename: Union[str, Path] = DEFAULT_IMAGE_SAVE_FILENAME) -> None:
        """
        Saves one or more Docker images to a single .tar archive.

        Args:
            image_names: A list of image names (e.g., ["ubuntu:latest", "my-app:1.0"]).
            output_filename: The name of the output .tar file.
        """
        if not image_names:
            raise DockerImageError("No image names provided for saving.")

        self._check_docker_daemon_status()

        # Check if all specified images exist. If not, raise an error.
        missing_images = [
            img for img in image_names if not self._is_image_present(img)]
        if missing_images:
            raise DockerImageError(
                f"Cannot save images. The following specified images are not found locally: {', '.join(missing_images)}"
            )

        # Use Path for output_path
        output_path = Path(output_filename).resolve()
        output_parent_dir = output_path.parent  # Use Path.parent

        try:
            output_parent_dir.mkdir(
                parents=True, exist_ok=True)  # Use Path.mkdir
            info(f"Created output directory: {output_parent_dir}")
        except OSError as e:
            raise DockerImageError(
                f"Failed to create output directory '{output_parent_dir}': {e}"
            )

        info(
            f"Saving Docker images {', '.join(image_names)} to '{output_path}'..."
        )
        try:
            # Docker save command directly to Path string
            execute_docker_command(
                ["save", "-o", str(output_path)] + image_names, capture_output=False, check=True
            )
            info(f"Successfully saved images to '{output_path}'.")
        except CommandExecutionError as e:
            raise DockerImageError(
                f"Failed to save Docker images: {e.stderr.strip()}" if e.stderr else str(e))
        except Exception as e:
            raise DockerImageError(
                f"An unexpected error occurred during image saving: {e}"
            )

    def load_images(self, input_path: Union[str, Path]) -> None:
        """
        Loads Docker images from a .tar archive.

        Args:
            input_path: Path to the .tar archive file. Can be a local path or a URL
                        (http, https, ftp).
        """
        self._check_docker_daemon_status()

        local_archive_path: Optional[Path] = None  # Change type hint to Path
        try:
            # FileLoader's fetch method should handle downloading and return a Path object.
            # It also manages its own temporary directories. No need for TEMP_DOWNLOAD_DIR here.
            info(f"Attempting to fetch image archive from: {input_path}")
            local_archive_path = Path(self.file_fetcher.fetch(
                str(input_path)))  # Ensure input is string for fetch

            # The check `if not os.path.exists(local_archive_path)` is redundant if fetch is robust.
            # If fetch fails, it should raise FileFetcherError.

            info(f"Loading Docker images from '{local_archive_path}'...")
            execute_docker_command(
                ["load", "-i", str(local_archive_path)], capture_output=False, check=True
            )
            info(f"Successfully loaded images from '{local_archive_path}'.")
            info("You can verify loaded images by running 'docker images'.")
        except FileFetcherError as e:
            raise DockerImageError(f"Failed to fetch image archive: {e}")
        except CommandExecutionError as e:
            raise DockerImageError(
                f"Failed to load Docker images: {e.stderr.strip()}" if e.stderr else str(e))
        except Exception as e:
            raise DockerImageError(
                f"An unexpected error occurred during image loading: {e}"
            )
        finally:
            self.file_fetcher.cleanup_temp_files()

    def list_images(self) -> None:
        """Lists all local Docker images."""
        info("Listing local Docker images...")
        try:
            self._check_docker_daemon_status()  # Ensure daemon is running before listing
            # `check=True` will raise CommandExecutionError on failure.
            execute_docker_command(
                ["images"], capture_output=False, check=True)
            info("Docker images listed.")
        except CommandExecutionError as e:
            raise DockerImageError(
                f"Failed to list Docker images: {e.stderr.strip()}" if e.stderr else str(e))
        except DockerImageError as e:  # Re-raise DockerImageError from _check_docker_daemon_status
            # Allow higher level to catch and handle. No sys.exit(1) here.
            raise e
        except Exception as e:
            raise DockerImageError(
                f"An unexpected error occurred during image listing: {e}")
