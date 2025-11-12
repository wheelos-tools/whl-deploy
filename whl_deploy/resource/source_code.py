#!/usr/bin/env python3

import sys
import shutil
from pathlib import Path
from typing import Optional, Union

from whl_deploy.common import info, warning, error, critical
from whl_deploy.common import ensure_dir
from whl_deploy.file_loader import FileLoader, FileFetcherError
from whl_deploy.archive_manager import ArchiveManager, ArchiveManagerError


class SourcePackageManagerError(Exception):
    """Custom exception for SourcePackageManager specific errors."""

    pass


# --- Configuration Constants ---
# Default directory where source code will be "active" or assumed to be for operations.
DEFAULT_SOURCE_DIR = Path("apollo")

# Default filename for exported source packages
DEFAULT_SOURCE_EXPORT_FILENAME = "source_code.tar.gz"

# --- SourcePackageManager Implementation ---


class SourcePackageManager:
    """
    Manages the import, export, and clearing of source code packages.
    The 'DEFAULT_SOURCE_DIR' represents a default location for source code operations
    (e.g., as a default source for export/clear, or a default target for import).
    Import operations can explicitly target any location.
    """

    def __init__(self, source_code_dir: Optional[Path] = None):
        """
        Initializes the SourcePackageManager.

        Args:
            default_managed_dir: Optional. The default directory this manager considers
                                 the "active" or "managed" source code location.
                                 If None, DEFAULT_SOURCE_DIR is used.
        """
        # This will be the default directory for operations like `clear`
        # and `export` if no specific path is provided.
        self.source_code_dir: Path = (
            source_code_dir if source_code_dir else DEFAULT_SOURCE_DIR
        )

        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()

        info(
            f"Initialized SourcePackageManager. Default managed source directory: {self.source_code_dir}"
        )

    def _prepare_target_directory(
        self, target_dir: Path, force_overwrite: bool
    ) -> None:
        """
        Prepares the target directory for new content.
        Cleans existing content or raises an error if force_overwrite is False.

        Args:
            target_dir: The pathlib.Path object for the target directory.
            force_overwrite: If True, overwrite existing content without asking.
                             If False, raises SourcePackageManagerError if target_dir is not empty.
        Raises:
            SourcePackageManagerError: If target_dir is not empty and force_overwrite is False.
        """
        if not target_dir.exists():
            info(
                f"Target directory '{target_dir}' does not exist. Skipping preparation."
            )
            return  # Directory does not exist, do nothing as requested.

        # If we reach here, target_dir exists. Now check its content.
        dir_not_empty = any(target_dir.iterdir())

        if dir_not_empty:
            if not force_overwrite:
                raise SourcePackageManagerError(
                    f"Target directory '{target_dir}' is not empty. "
                    "Cannot proceed without force_overwrite=True. "
                    "Please clear it manually or set force_overwrite to True."
                )

            info(
                f"Force overwrite enabled. Cleaning up existing content in directory: {target_dir}"
            )
            try:
                shutil.rmtree(target_dir)
                info(f"Successfully cleaned old content from '{target_dir}'.")
            except OSError as e:
                raise SourcePackageManagerError(
                    f"Failed to clean up existing content in '{target_dir}': {e}. "
                    "Please check permissions or if the directory is in use."
                )
        else:
            info(f"Target directory '{target_dir}' is empty. Proceeding.")

    def import_source_package(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path] = ".",
        force_overwrite: bool = True,
    ) -> None:
        """
        Imports source code from a .tar.gz archive (local file or URL)
        to a specified output directory.

        Args:
            input_path: Path to the local .tar.gz archive file OR URL of the archive.
            output_path: The directory where the source code will be extracted.
                         Defaults to current directory.
            force_overwrite: If True, overwrite existing content in output_path without asking.
                             If False and output_path is not empty, will raise an error.
        """
        target_directory = Path(output_path).resolve().parent

        info(
            f"Starting import of source package from '{input_path}' to '{target_directory}'..."
        )

        try:
            self._prepare_target_directory(output_path, force_overwrite)
        except SourcePackageManagerError as e:
            error(f"Source package import preparation failed: {e}")
            raise  # Re-raise to signal a failure to the caller

        local_archive_path: Optional[Path] = None
        try:
            # Fetch the archive, which might download it to a temp location
            local_archive_path = Path(self.file_fetcher.fetch(str(input_path)))

            info(
                f"Extracting source code archive '{local_archive_path}' to '{target_directory}'..."
            )

            self.archive_manager.decompress(
                local_archive_path,
                target_directory,
                target_top_level_dir_name=DEFAULT_SOURCE_DIR.name,
            )

            info(f"Source code imported successfully to '{target_directory}'!")

        except FileFetcherError as e:
            raise SourcePackageManagerError(
                f"Failed to fetch source code archive from '{input_path}': {e}"
            )
        except ArchiveManagerError as e:
            raise SourcePackageManagerError(
                f"Failed to extract source code archive '{local_archive_path}' to '{target_directory}': {e}"
            )
        except OSError as e:  # Catch OS-level errors during file operations
            raise SourcePackageManagerError(
                f"File system error during import to '{target_directory}': {e}"
            )
        except Exception as e:  # Catch any other unexpected errors
            critical(
                f"An unexpected error occurred during source code import: {e}",
                exc_info=True,
            )
            raise SourcePackageManagerError(f"An unexpected error occurred: {e}")
        finally:
            # TODO(zero): Ensure temporary files from FileLoader are cleaned up
            # self.file_fetcher.cleanup_temp_files()
            pass

    def export_source_package(
        self,
        input_path: Union[str, Path] = DEFAULT_SOURCE_DIR,
        output_path: Union[str, Path] = DEFAULT_SOURCE_EXPORT_FILENAME,
    ) -> None:
        """
        Exports a source code directory to a .tar.gz archive.

        Args:
            input_path: The directory containing the source code to be exported.
                        Defaults to DEFAULT_SOURCE_DIR.
            output_path: The full path and filename for the output .tar.gz file (e.g., "my_project.tar.gz").
                         Defaults to DEFAULT_SOURCE_EXPORT_FILENAME.
        """
        source_directory = Path(input_path).resolve()
        output_file_path = Path(output_path).resolve()

        info(
            f"Preparing to export source code from '{source_directory}' to '{output_file_path}'."
        )

        # Ensure the source directory for export exists and is accessible
        ensure_dir(source_directory)

        # Validate source directory
        if not source_directory.is_dir():
            raise SourcePackageManagerError(
                f"Source directory '{source_directory}' does not exist or is not a directory. Nothing to export."
            )
        if not any(source_directory.iterdir()):
            warning(
                f"Source directory '{source_directory}' is empty. Exporting an empty archive."
            )

        # Ensure parent directory for output exists
        ensure_dir(output_file_path.parent)

        try:
            info(
                f"Compressing source code from '{source_directory}' to '{output_file_path}'..."
            )
            self.archive_manager.compress(source_directory, output_file_path)
            info(f"Source code exported successfully to '{output_file_path}'!")
        except ArchiveManagerError as e:
            raise SourcePackageManagerError(
                f"Failed to export source code from '{source_directory}' to '{output_file_path}': {e}"
            )
        except OSError as e:  # Catch OS-level errors during file operations
            raise SourcePackageManagerError(
                f"File system error during export to '{output_file_path}': {e}"
            )
        except Exception as e:  # Catch any other unexpected errors
            critical(
                f"An unexpected error occurred during source code export: {e}",
                exc_info=True,
            )
            raise SourcePackageManagerError(f"An unexpected error occurred: {e}")

    def clear_source_package(self, force_clear: bool = False) -> None:
        """
        Clears the default managed source code directory (self.source_code_dir).

        Args:
            force_clear: If True, clear the directory without requiring confirmation.
                         If False and the directory is not empty, will raise an error.
        """
        info(f"Preparing to clear source package at '{self.source_code_dir}'.")

        # Ensure the directory exists before trying to clear it
        ensure_dir(self.source_code_dir)

        if not any(self.source_code_dir.iterdir()):
            info(
                f"Source package directory '{self.source_code_dir}' is already empty. Nothing to clear."
            )
            return

        # If not empty and not forced, raise an error
        if not force_clear:
            raise SourcePackageManagerError(
                f"Source package directory '{self.source_code_dir}' is not empty. "
                "Cannot proceed without --force (or equivalent) to clear existing content. "
                "Please run with --force."
            )

        try:
            info(f"Deleting all contents in '{self.source_code_dir}'...")
            shutil.rmtree(self.source_code_dir)

            # Re-create the directory after deletion to ensure it exists for future use
            ensure_dir(self.source_code_dir)
            info(f"Source package at '{self.source_code_dir}' cleared successfully!")
        except OSError as e:
            raise SourcePackageManagerError(
                f"Failed to clear source package directory '{self.source_code_dir}': {e}. "
                "Please check permissions or if the directory is in use."
            )
        except Exception as e:
            critical(
                f"An unexpected error occurred during source package clear: {e}",
                exc_info=True,
            )
            raise SourcePackageManagerError(
                f"An unexpected error occurred during source package clear: {e}"
            )
