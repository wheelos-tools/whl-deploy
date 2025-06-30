#!/usr/bin/env python3

from pathlib import Path
from typing import List, Optional, Union

from whl_deploy.common import (
    execute_docker_command,
    CommandExecutionError,
    info, warning, error, critical
)

from whl_deploy.file_loader import FileLoader, FileFetcherError

# --- Configuration Constants ---
DEFAULT_IMAGE_NAME = "registry.baidubce.com/apolloauto/apollo:dev-x86_64-18.04-20221124_1708"
DEFAULT_IMAGE_EXPORT_FILENAME = "docker_image.tar"


class DockerImageError(Exception):
    """Custom exception for errors during Docker image operations."""
    pass

# --- DockerImageManager Implementation ---


class DockerImageManager:
    def __init__(self):
        self.file_fetcher = FileLoader()
        info("Initialized DockerImageManager.")

    def _check_docker_daemon_status(self) -> None:
        """
        Checks if Docker daemon is running and accessible.

        Raises:
            DockerImageError: If Docker daemon is not running, Docker is not installed,
                              or any other error occurs during the check.
        """
        info("Checking Docker daemon status...")
        try:
            # Using `docker info` is robust for checking daemon connectivity.
            # `check=True` ensures an exception is raised on non-zero exit code.
            # `capture_output=True` is useful for debugging if an error occurs.
            execute_docker_command(["info"], capture_output=False, check=True)
            info("Docker daemon is active.")
        except CommandExecutionError as e:
            stderr_output = e.stderr.lower() if e.stderr else ""
            if "cannot connect to the docker daemon" in stderr_output or "permission denied" in stderr_output:
                critical_msg = (
                    "Docker daemon is not running or accessible. Please ensure:\n"
                    "  1. Docker Desktop/Engine is running.\n"
                    "  2. Your user has permissions to access the Docker daemon (e.g., added to 'docker' group).\n"
                    f"Error details: {e.stderr.strip()}" if e.stderr else "No detailed error message."
                )
                critical(critical_msg)
                raise DockerImageError(critical_msg)
            else:
                critical_msg = (
                    f"Failed to check Docker daemon status due to unexpected command error: {e.stderr.strip()}"
                    if e.stderr else f"Command '{' '.join(e.cmd)}' failed with exit code {e.returncode}."
                )
                critical(critical_msg)
                raise DockerImageError(critical_msg)
        except FileNotFoundError:
            critical(
                "Docker command not found. Please ensure Docker is installed and in your system's PATH.")
            raise DockerImageError(
                "Docker command not found. Please ensure Docker is installed and in your PATH."
            )
        except Exception as e:
            critical(
                f"An unexpected error occurred while checking Docker daemon status: {e}", exc_info=True)
            raise DockerImageError(
                f"An unexpected error occurred while checking Docker daemon status: {e}"
            )

    def _get_image_id(self, image_name_or_id: str) -> Optional[str]:
        """
        Attempts to get the full image ID for a given image name or ID.
        Returns None if the image is not found.
        """
        try:
            # Use docker inspect for a robust check.
            # If the image doesn't exist, this will raise CommandExecutionError.
            result = execute_docker_command(
                ["inspect", "--format", "{{.Id}}", image_name_or_id],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except CommandExecutionError as e:
            # `docker inspect` with `check=True` will raise CommandExecutionError if image not found.
            # No need to check stderr for "No such image" explicitly,
            # as the non-zero exit code already indicates non-existence or an issue.
            # We assume non-zero exit for inspect means image not found for this context.
            info(
                f"Image '{image_name_or_id}' not found locally (inspect failed with exit code {e.returncode}).")
            return None
        except Exception as e:
            warning(
                f"An unexpected error occurred while inspecting image '{image_name_or_id}': {e}", exc_info=True)
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

    def save_images(self, image_name: str, output_filename: Union[str, Path] = DEFAULT_IMAGE_EXPORT_FILENAME) -> None:
        """
        Saves a single Docker image to a .tar archive.

        Args:
            image_name: The name of the image to save (e.g., "ubuntu:latest").
            output_filename: The name/path of the output .tar file.
        """
        if not image_name:
            raise DockerImageError("No image name provided for saving.")

        self._check_docker_daemon_status()

        # Validate that the specified image exists locally before attempting to save
        if not self._is_image_present(image_name):
            raise DockerImageError(
                f"Cannot save image. The specified image is not found locally: {image_name}"
            )

        output_path = Path(output_filename).resolve()
        output_parent_dir = output_path.parent

        # Ensure the output directory exists
        try:
            output_parent_dir.mkdir(parents=True, exist_ok=True)
            info(f"Ensured output directory exists: {output_parent_dir}")
        except OSError as e:
            raise DockerImageError(
                f"Failed to create output directory '{output_parent_dir}': {e}"
            )

        info(f"Saving Docker image '{image_name}' to '{output_path}'...")
        try:
            # Docker save command directly to Path string
            # The docker command expects individual image names, not a list in one argument.
            execute_docker_command(
                ["save", "-o", str(output_path), image_name], capture_output=False, check=True
            )
            info(
                f"Successfully saved image '{image_name}' to '{output_path}'.")
        except CommandExecutionError as e:
            critical(
                f"Failed to save Docker image: {e.stderr.strip()}" if e.stderr else str(e))
            raise DockerImageError(
                f"Failed to save Docker image: {e.stderr.strip()}" if e.stderr else str(e))
        except Exception as e:
            critical(
                f"An unexpected error occurred during image saving: {e}", exc_info=True)
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

        # Resolve input early for existence check
        resolved_input_path = Path(input_path)

        # Pre-check if the local file exists, if it's not a URL
        if not resolved_input_path.is_absolute() or not resolved_input_path.exists():
            # If not an absolute path or doesn't exist locally, assume FileLoader will fetch it.
            # If fetch fails for a non-existent local file, FileFetcherError will be raised.
            pass
        elif not resolved_input_path.is_file():
            raise DockerImageError(
                f"Input path '{resolved_input_path}' is not a file.")

        local_archive_path: Path  # Final path after fetching

        try:
            # FileLoader's fetch method should handle downloading and return a Path object.
            info(f"Attempting to fetch image archive from: {input_path}")
            local_archive_path = Path(self.file_fetcher.fetch(str(input_path)))

            info(f"Loading Docker images from '{local_archive_path}'...")
            execute_docker_command(
                ["load", "-i", str(local_archive_path)], capture_output=False, check=True
            )
            info(f"Successfully loaded images from '{local_archive_path}'.")
            info("You can verify loaded images by running 'docker images'.")
        except FileFetcherError as e:
            critical(f"Failed to fetch image archive: {e}")
            raise DockerImageError(f"Failed to fetch image archive: {e}")
        except CommandExecutionError as e:
            critical(
                f"Failed to load Docker images: {e.stderr.strip()}" if e.stderr else str(e))
            raise DockerImageError(
                f"Failed to load Docker images: {e.stderr.strip()}" if e.stderr else str(e))
        except Exception as e:
            critical(
                f"An unexpected error occurred during image loading: {e}", exc_info=True)
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
            execute_docker_command(
                ["images"], capture_output=False, check=True)
            info("Docker images listed.")
        except CommandExecutionError as e:
            critical(
                f"Failed to list Docker images: {e.stderr.strip()}" if e.stderr else str(e))
            raise DockerImageError(
                f"Failed to list Docker images: {e.stderr.strip()}" if e.stderr else str(e))
        except DockerImageError as e:  # Re-raise DockerImageError from _check_docker_daemon_status
            raise e
        except Exception as e:
            critical(
                f"An unexpected error occurred during image listing: {e}", exc_info=True)
            raise DockerImageError(
                f"An unexpected error occurred during image listing: {e}")

    def get_local_image_tags(self) -> List[str]:
        """
        Returns a list of local Docker image tags in 'REPOSITORY:TAG' format.
        """
        self._check_docker_daemon_status()
        info("Fetching local Docker image tags...")
        try:
            # Use --format to get only repository and tag, and filter out <none>:<none>
            result = execute_docker_command(
                ["images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True,
                check=True
            )
            tags = [line.strip() for line in result.stdout.splitlines() if line.strip() and "<none>" not in line]
            info(f"Found {len(tags)} local image tags.")
            return tags
        except CommandExecutionError as e:
            warning(f"Failed to list local Docker image tags: {e.stderr.strip()}")
            return []
        except Exception as e:
            warning(f"An unexpected error occurred while fetching local image tags: {e}")
            return []
