#!/usr/bin/env python3

import os
import sys
import shutil
from pathlib import Path
from typing import List, Tuple, Optional

from whl_deploy.common import (
    info, warning, error, critical
)
from whl_deploy.file_loader import FileLoader, FileFetcherError
from whl_deploy.archive_manager import ArchiveManager, ArchiveManagerError


class SourcePackageManagerError(Exception):
    """Custom exception for SourcePackageManager specific errors."""
    pass


# --- Configuration Constants ---
# Base directory for all source related data
SOURCE_BASE_DIR = Path("/opt/apollo")  # Use Path
# The specific directory where the *active* source code will be stored
DEFAULT_ACTIVE_SOURCE_DIR = Path("/opt/apollo")  # Use Path

# Default filename for exported source packages
DEFAULT_EXPORT_FILENAME = "apollo_source_code.tar.gz"

# --- SourcePackageManager Implementation ---


class SourcePackageManager:
    """
    Manages the import and export of a single active autonomous driving source code package.
    """

    def __init__(self):
        # Convert to pathlib.Path objects and resolve to absolute paths
        self.source_base_dir = SOURCE_BASE_DIR.resolve()
        self.active_source_dir = DEFAULT_ACTIVE_SOURCE_DIR.resolve()

        # Pass the logger instance to FileLoader for consistent logging
        # Assuming common.info, etc. use a global logger,
        # or FileLoader itself handles its logging.
        # If common.py uses a shared logger, no need to pass an instance here unless specific.
        # Removed logger_instance=logger, assuming FileLoader logs directly or uses common's logger.
        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()  # Initialize ArchiveManager

        info(
            f"Initialized SourcePackageManager. Active source will be managed in: {self.active_source_dir}")

    def _check_root_permissions(self) -> None:
        """
        Checks if the script has necessary root privileges for critical operations.
        Raises PermissionError if write access is denied for crucial directories.
        """
        if os.geteuid() != 0:
            warning("It is highly recommended to run this script with root (sudo) privileges "
                    f"for operations on '{self.source_base_dir}'.")
            # Check write access to the parent directory of SOURCE_BASE_DIR
            # This ensures that even if /opt/apollo doesn't exist, we can create it.
            # Use Path.parent for parent directory.
            base_dir_parent = self.source_base_dir.parent
            if not os.access(base_dir_parent, os.W_OK):
                raise PermissionError(f"No write access to '{base_dir_parent}'. "
                                      "Please run with sudo to create/manage source directories.")
        else:
            info("Running with root privileges.")

    def _ensure_source_base_dir(self) -> None:
        """Ensures the source base directory (/opt/apollo) exists and has correct permissions."""
        try:
            # Use Path.mkdir for creating directory, with exist_ok=True and mode.
            self.source_base_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
            info(
                f"Ensured source base directory exists: {self.source_base_dir}")
        except OSError as e:
            raise SourcePackageManagerError(
                f"Failed to create source base directory '{self.source_base_dir}': {e}")
        try:
            # Ensure permissions are correct even if it already exists
            # Use Path.chmod for setting permissions
            self.source_base_dir.chmod(0o755)
        except OSError as e:
            raise SourcePackageManagerError(
                f"Failed to set permissions for '{self.source_base_dir}': {e}")

    def _prepare_active_source_directory(self, force_overwrite: bool) -> None:
        """
        Prepares the active source directory for new content.
        Cleans existing content or prompts for overwrite.
        """
        dir_exists = self.active_source_dir.is_dir()  # Use Path.is_dir()
        dir_not_empty = dir_exists and bool(
            list(self.active_source_dir.iterdir()))  # Use Path.iterdir()

        if dir_not_empty:
            if not force_overwrite:
                warning(
                    f"Existing source code found in '{self.active_source_dir}'.")
                if not sys.stdin.isatty():
                    raise SourcePackageManagerError(
                        "Existing source code found and running in non-interactive mode. "
                        "Use --force to overwrite or cancel manually."
                    )
                user_input = input(
                    "This operation will delete all existing contents. Continue? (y/N): ").strip().lower()
                if user_input != 'y':
                    info("Operation cancelled by user.")
                    raise SourcePackageManagerError(
                        "Import operation cancelled by user.")
            else:
                info("Force overwrite enabled. Proceeding to delete existing source code.")
        elif dir_exists and not dir_not_empty:  # Directory exists but is empty
            info(
                f"Active source directory '{self.active_source_dir}' exists but is empty. Proceeding with import.")
        else:  # Directory does not exist
            info(
                f"Active source directory '{self.active_source_dir}' does not exist. It will be created.")

        # Clean up or create the directory
        if self.active_source_dir.exists():  # Use Path.exists()
            try:
                shutil.rmtree(self.active_source_dir)
                info(
                    f"Successfully deleted old source code from '{self.active_source_dir}'.")
            except OSError as e:
                raise SourcePackageManagerError(
                    f"Failed to clean up existing source code in '{self.active_source_dir}': {e}")

        try:
            # Use Path.mkdir for creating directory, with exist_ok=True and mode.
            self.active_source_dir.mkdir(
                mode=0o755, parents=True, exist_ok=True)
            info(
                f"Prepared active source directory: '{self.active_source_dir}'.")
        except OSError as e:
            raise SourcePackageManagerError(
                f"Failed to create/prepare active source directory '{self.active_source_dir}': {e}")

    def import_source_package(self, source_path: str, force_overwrite: bool = False) -> None:
        """
        Imports source code from a .tar.gz archive (local file or URL)
        to the fixed active source directory (DEFAULT_ACTIVE_SOURCE_DIR).
        This will overwrite any existing source code in that directory.

        Args:
            source_path: Path to the local .tar.gz archive file OR URL of the archive.
            force_overwrite: If True, overwrite existing source code without asking.
        """
        self._check_root_permissions()
        self._ensure_source_base_dir()

        try:
            self._prepare_active_source_directory(force_overwrite)
        except SourcePackageManagerError as e:
            # If user cancels, _prepare_active_source_directory raises this error
            error(f"Import preparation failed: {e}")
            return  # Exit gracefully if cancelled

        local_archive_path: Optional[Path] = None  # Use Path
        try:
            # FileLoader should handle its own temporary directories.
            # No need to pass destination_dir=os.getcwd().
            local_archive_path = Path(self.file_fetcher.fetch(source_path))

            info(
                f"Extracting source code archive '{local_archive_path}' to '{self.active_source_dir}'...")

            self.archive_manager.decompress(
                local_archive_path, self.active_source_dir)

            info(
                f"Source code imported successfully to '{self.active_source_dir}'!")

        except FileFetcherError as e:
            raise SourcePackageManagerError(
                f"Failed to fetch source code archive: {e}")
        except ArchiveManagerError as e:  # Catch the specific exception from ArchiveManager
            raise SourcePackageManagerError(
                f"Failed to extract source code archive '{local_archive_path}': {e}")
        except Exception as e:
            critical(
                f"An unexpected error occurred during source code import: {e}")
            raise  # Re-raise to be caught by main's error handler
        finally:
            self.file_fetcher.cleanup_temp_files()

    def export_source_package(self, output_filename: str = DEFAULT_EXPORT_FILENAME) -> None:
        """
        Exports the currently active source code directory to a .tar.gz archive.

        Args:
            output_filename: The name of the output .tar.gz file.
        """
        self._check_root_permissions()

        source_code_to_export = self.active_source_dir

        # Use Path.is_dir() and Path.iterdir()
        if not source_code_to_export.is_dir() or not list(source_code_to_export.iterdir()):
            raise SourcePackageManagerError(f"Active source code directory '{source_code_to_export}' "
                                            "does not exist or is empty. Nothing to export.")

        output_path = Path(output_filename).resolve()  # Use Path and resolve()

        try:
            self.archive_manager.compress(source_code_to_export, output_path)
            info(
                f"Active source code exported successfully to '{output_path}'!")
        except ArchiveManagerError as e:  # Catch the specific exception from ArchiveManager
            raise SourcePackageManagerError(
                f"Failed to export active source code to '{output_path}': {e}")
        except Exception as e:
            raise SourcePackageManagerError(
                f"An unexpected error occurred during source code export: {e}")
