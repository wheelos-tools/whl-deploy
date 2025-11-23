#!/usr/bin/env python3

import os
import sys
import shutil
from pathlib import Path
from typing import Optional, Union

from whl_deploy.utils.common import info, warning, error, critical
from whl_deploy.utils.file_loader import FileLoader, FileFetcherError
from whl_deploy.utils.archive_manager import ArchiveManager, ArchiveManagerError
from whl_deploy.host.config import WORKSPACE

# --- Configuration Constants ---
MAP_IMPORT_DIR = "modules/map/data"
DEFAULT_MAP_IMPORT_DIR = WORKSPACE / MAP_IMPORT_DIR

# Still recommend .tar.gz as default
DEFAULT_MAP_EXPORT_FILENAME = "map_data.tar.gz"

# Only import and export, no management.


class MapManagerError(Exception):
    """Custom exception for errors during map operations."""

    pass


class MapManager:
    def __init__(self, base_dir: Union[str, Path] = DEFAULT_MAP_IMPORT_DIR):
        self.map_base_dir = Path(base_dir).resolve()
        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()
        info(f"Initialized MapManager with base directory: {self.map_base_dir}")

    def _check_permissions(self) -> None:
        """Checks if the script has necessary permissions for map operations."""

        # Check write access to the base directory itself if it exists.
        # If it doesn't exist, check parent for creation permission.
        if self.map_base_dir.exists():
            if not os.access(self.map_base_dir, os.W_OK):
                raise PermissionError(
                    f"No write access to '{self.map_base_dir}'. "
                    "Please run with sudo."
                )
        else:  # map_base_dir does not exist
            if not os.access(self.map_base_dir.parent, os.W_OK):
                raise PermissionError(
                    f"No write access to create '{self.map_base_dir}'. "
                    "Please run with sudo."
                )

    def _ensure_base_dir_exists(self) -> None:
        """Ensures the map base directory exists and has appropriate permissions."""
        info(
            f"Ensuring map base directory '{self.map_base_dir}' exists and has correct permissions..."
        )
        try:
            self.map_base_dir.mkdir(parents=True, exist_ok=True)
            self.map_base_dir.chmod(0o755)
            info(
                f"Map base directory '{self.map_base_dir}' is prepared with permissions 0755."
            )
        except OSError as e:
            raise MapManagerError(
                f"Failed to prepare map base directory '{self.map_base_dir}': {e}. "
                "Please check system permissions."
            )

    def import_map(
        self, source_path: str, map_name: str, force_overwrite: bool = False
    ) -> None:
        """
        Imports map data from a compressed archive (local file or URL)
        to a new subdirectory within the map base directory.

        Args:
            source_path: Path to the local archive file or URL of the archive.
            map_name: The name of the map. This will be the name of the subdirectory.
            force_overwrite: If True, overwrite existing map without asking.
        """
        self._check_permissions()
        self._ensure_base_dir_exists()

        target_map_dir = self.map_base_dir / map_name

        # --- Handle existing map directory ---
        # The logic here is: if target_map_dir exists and is not empty,
        # either confirm overwrite or exit. If force_overwrite, or confirmed,
        # then delete the existing directory.
        if target_map_dir.exists() and any(
            target_map_dir.iterdir()
        ):  # Check if exists AND not empty
            if not force_overwrite:
                warning(
                    f"Map directory '{target_map_dir}' already exists and is not empty."
                )
                if not sys.stdin.isatty():
                    raise MapManagerError(
                        "Existing map found and running in non-interactive mode. "
                        "Use --force to overwrite or delete manually first."
                    )
                user_input = input("Overwrite existing map? (y/N): ").strip().lower()
                if user_input != "y":
                    info("Map import cancelled by user.")
                    return  # Exit without doing anything
            else:
                info(
                    f"Force overwrite enabled. Deleting existing map at '{target_map_dir}'."
                )
                # No need to call delete_map here if we're going to rmtree and mkdir later
                # Just proceed to clean up
                try:
                    shutil.rmtree(target_map_dir)
                    info(f"Existing map '{target_map_dir}' removed.")
                except OSError as e:
                    raise MapManagerError(
                        f"Failed to remove existing map '{target_map_dir}': {e}"
                    )
        elif target_map_dir.exists() and not any(target_map_dir.iterdir()):
            info(
                f"Map directory '{target_map_dir}' exists but is empty. Proceeding with import."
            )
            # Still remove empty dir to ensure clean state and correct permissions are applied below
            try:
                shutil.rmtree(target_map_dir)
            except OSError as e:
                warning(
                    f"Failed to remove empty directory '{target_map_dir}': {e}. Continuing anyway."
                )

        archive_to_extract_path: Optional[Path] = None
        try:
            archive_to_extract_path = Path(self.file_fetcher.fetch(source_path))

            # Create the target map directory before extraction
            # This mkdir should always succeed now because previous logic handles pre-existence
            # Ensure it's created clean
            target_map_dir.mkdir(parents=True, exist_ok=False)
            target_map_dir.chmod(0o755)

            info(
                f"Extracting map archive '{archive_to_extract_path}' to '{target_map_dir}'..."
            )

            self.archive_manager.decompress(archive_to_extract_path, target_map_dir)

            info(f"Map '{map_name}' imported successfully to '{target_map_dir}'!")

        except FileFetcherError as e:
            # Re-raise as MapManagerError, and ensure cleanup happens in finally
            raise MapManagerError(f"Failed to fetch map archive: {e}")
        except ArchiveManagerError as e:
            # Re-raise as MapManagerError, and ensure cleanup happens in finally
            raise MapManagerError(f"Failed to decompress map archive: {e}")
        except Exception as e:
            # Catch all other unexpected exceptions
            raise MapManagerError(
                f"An unexpected error occurred during map import: {e}"
            )
        finally:
            # Always clean up target_map_dir if import failed, regardless of force_overwrite.
            # An incomplete/failed import is unusable.
            self.file_fetcher.cleanup_temp_files()
            if target_map_dir.exists() and (
                (
                    "Failed to fetch" in str(sys.exc_info()[1])  # If fetch failed
                    or "Failed to decompress" in str(sys.exc_info()[1])
                )  # If decompress failed
                # If MapManagerError was raised
                or (
                    sys.exc_info()[0] is not None
                    and isinstance(sys.exc_info()[0](), MapManagerError)
                )
                # Check if an exception was raised, and if it was not a user cancellation
                and not ("cancelled by user" in str(sys.exc_info()[1]))
            ):
                error(
                    f"Cleaning up partially imported map directory '{target_map_dir}' due to import failure."
                )
                try:
                    shutil.rmtree(target_map_dir)
                except OSError as e:
                    critical(
                        f"Failed to clean up partially imported map '{target_map_dir}': {e}"
                    )

    def export_map(
        self,
        map_name: str,
        output_filename: Union[str, Path] = DEFAULT_MAP_EXPORT_FILENAME,
    ) -> None:
        """
        Exports a specific map directory to a compressed archive.

        Args:
            map_name: The name of the map directory to export.
            output_filename: The name of the output archive file (e.g., "my_map.tar.gz").
        """
        self._check_permissions()

        source_map_dir = self.map_base_dir / map_name

        if not source_map_dir.is_dir():
            raise MapManagerError(
                f"Source map directory '{source_map_dir}' does not exist or is not a directory. "
                "Nothing to export."
            )

        output_path = Path(output_filename).resolve()

        # Ensure output directory exists (parent of output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        info(f"Ensured output directory exists: {output_path.parent}")

        info(
            f"Compressing map '{map_name}' from '{source_map_dir}' to '{output_path}'..."
        )

        try:
            # Pass map_name as arcname_in_archive so the archive contains a top-level dir named map_name
            self.archive_manager.compress(
                source_map_dir, output_path, arcname_in_archive=map_name
            )

            info(f"Map '{map_name}' exported successfully to '{output_path}'!")
        except ArchiveManagerError as e:
            raise MapManagerError(f"Failed to export map: {e}")
        except Exception as e:
            raise MapManagerError(
                f"An unexpected error occurred during map export: {e}"
            )

    def list_maps(self) -> None:
        """Lists all maps currently stored in the map base directory."""
        info(f"Listing maps in '{self.map_base_dir}'...")

        if not self.map_base_dir.is_dir():
            info(
                f"Map base directory '{self.map_base_dir}' does not exist. No maps found."
            )
            return

        maps = [d.name for d in self.map_base_dir.iterdir() if d.is_dir()]

        if not maps:
            info(f"No maps found in '{self.map_base_dir}'.")
            return

        info("Available Maps:")
        for m in sorted(maps):
            info(f"  - {m}")
        info("Map listing complete.")

    def delete_map(self, map_name: str, force: bool = False) -> None:
        """
        Deletes a specific map directory.

        Args:
            map_name: The name of the map directory to delete.
            force: If True, delete without prompting for confirmation.
        """
        self._check_permissions()

        target_map_dir = self.map_base_dir / map_name

        if not target_map_dir.is_dir():
            raise MapManagerError(
                f"Map directory '{target_map_dir}' does not exist or is not a directory. "
                "Nothing to delete."
            )

        if not force:
            warning(
                f"You are about to delete the map: '{target_map_dir}'. This action cannot be undone."
            )
            if not sys.stdin.isatty():
                raise MapManagerError(
                    "Deleting map in non-interactive mode requires --force. "
                    "Please use 'delete <map_name> --force' or delete manually."
                )
            user_input = (
                input("Are you sure you want to proceed? (y/N): ").strip().lower()
            )
            if user_input != "y":
                info("Map deletion cancelled by user.")
                return

        info(f"Deleting map: '{target_map_dir}'...")
        try:
            shutil.rmtree(target_map_dir)
            info(f"Map '{map_name}' deleted successfully from '{self.map_base_dir}'.")
        except OSError as e:
            raise MapManagerError(
                f"Failed to delete map '{target_map_dir}': {e}. "
                "Please check permissions or if the directory is in use."
            )
        except Exception as e:
            raise MapManagerError(
                f"An unexpected error occurred during map deletion: {e}"
            )
