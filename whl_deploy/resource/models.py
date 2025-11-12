#!/usr/bin/env python3

import os
import sys
import shutil
from pathlib import Path
from typing import Optional, Union, List

from whl_deploy.common import info, warning, error, critical

from whl_deploy.file_loader import FileLoader, FileFetcherError
from whl_deploy.archive_manager import ArchiveManager, ArchiveManagerError


# --- Configuration Constants ---
DEFAULT_MODEL_IMPORT_DIR = Path("modules/perception/production/data/perception")
DEFAULT_MODEL_EXPORT_FILENAME = "model_data.tar.gz"

# --- Custom Exception for Model Operations ---
# Only import and export, no management.


class ModelManagerError(Exception):
    """Custom exception for errors during model operations."""

    pass


# --- ModelManager Implementation ---


class ModelManager:
    def __init__(self, base_dir: Union[str, Path] = DEFAULT_MODEL_IMPORT_DIR):
        self.model_base_dir = Path(base_dir).resolve()
        self.file_fetcher = FileLoader()
        self.archive_manager = ArchiveManager()
        info(f"Initialized ModelManager with base directory: {self.model_base_dir}")

    def _check_permissions(self) -> None:
        """Checks if the script has necessary permissions for model operations."""

        if self.model_base_dir.exists():
            if not os.access(self.model_base_dir, os.W_OK):
                raise PermissionError(
                    f"No write access to '{self.model_base_dir}'. "
                    "Please run with sudo."
                )
        else:  # model_base_dir does not exist
            if not os.access(self.model_base_dir.parent, os.W_OK):
                raise PermissionError(
                    f"No write access to create '{self.model_base_dir}'. "
                    "Please run with sudo."
                )

    def _ensure_base_dir_exists(self) -> None:
        """Ensures the model base directory exists and has appropriate permissions."""
        info(
            f"Ensuring model base directory '{self.model_base_dir}' exists and has correct permissions..."
        )
        try:
            self.model_base_dir.mkdir(parents=True, exist_ok=True)
            self.model_base_dir.chmod(0o755)
            info(
                f"Model base directory '{self.model_base_dir}' is prepared with permissions 0755."
            )
        except OSError as e:
            raise ModelManagerError(
                f"Failed to prepare model base directory '{self.model_base_dir}': {e}. "
                "Please check system permissions."
            )

    def import_model(
        self, source_path: str, model_name: str, force_overwrite: bool = False
    ) -> None:
        """
        Imports model data from a compressed archive (local file or URL)
        to a new subdirectory within the model base directory.

        Args:
            source_path: Path to the local .tar.gz archive file or URL of the archive.
            model_name: The name of the model. This will be the name of the subdirectory.
            force_overwrite: If True, overwrite existing model without asking.
        """
        self._check_permissions()
        self._ensure_base_dir_exists()

        target_model_dir = self.model_base_dir / model_name

        if target_model_dir.exists() and any(
            target_model_dir.iterdir()
        ):  # Check if exists AND not empty
            if not force_overwrite:
                warning(
                    f"Model directory '{target_model_dir}' already exists and is not empty."
                )
                if not sys.stdin.isatty():
                    raise ModelManagerError(
                        "Existing model found and running in non-interactive mode. "
                        "Use --force to overwrite or delete manually first."
                    )
                user_input = input("Overwrite existing model? (y/N): ").strip().lower()
                if user_input != "y":
                    info("Model import cancelled by user.")
                    return  # Exit without doing anything
            else:
                info(
                    f"Force overwrite enabled. Deleting existing model at '{target_model_dir}'."
                )
                try:
                    shutil.rmtree(target_model_dir)
                    info(f"Existing model '{target_model_dir}' removed.")
                except OSError as e:
                    raise ModelManagerError(
                        f"Failed to remove existing model '{target_model_dir}': {e}"
                    )
        elif target_model_dir.exists() and not any(target_model_dir.iterdir()):
            info(
                f"Model directory '{target_model_dir}' exists but is empty. Proceeding with import."
            )
            try:
                # Still remove empty dir for clean state
                shutil.rmtree(target_model_dir)
            except OSError as e:
                warning(
                    f"Failed to remove empty directory '{target_model_dir}': {e}. Continuing anyway."
                )

        archive_to_extract_path: Optional[Path] = None
        try:
            archive_to_extract_path = Path(self.file_fetcher.fetch(source_path))

            # Create the target model directory before extraction
            target_model_dir.mkdir(parents=True, exist_ok=False)
            target_model_dir.chmod(0o755)

            info(
                f"Extracting model archive '{archive_to_extract_path}' to '{target_model_dir}'..."
            )

            self.archive_manager.decompress(archive_to_extract_path, target_model_dir)

            info(f"Model '{model_name}' imported successfully to '{target_model_dir}'!")

        except FileFetcherError as e:
            raise ModelManagerError(f"Failed to fetch model archive: {e}")
        except ArchiveManagerError as e:  # Catch specific exception from ArchiveManager
            raise ModelManagerError(f"Failed to decompress model archive: {e}")
        except Exception as e:
            raise ModelManagerError(
                f"An unexpected error occurred during model import: {e}"
            )
        finally:
            self.file_fetcher.cleanup_temp_files()
            # Always clean up target_model_dir if import failed, regardless of force_overwrite.
            # An incomplete/failed import is unusable.
            if target_model_dir.exists() and (
                (
                    "Failed to fetch" in str(sys.exc_info()[1])  # If fetch failed
                    or "Failed to decompress" in str(sys.exc_info()[1])
                )  # If decompress failed
                # If ModelManagerError was raised
                or (
                    sys.exc_info()[0] is not None
                    and isinstance(sys.exc_info()[0](), ModelManagerError)
                )
                # Exclude user cancellation
                and not ("cancelled by user" in str(sys.exc_info()[1]))
            ):
                error(
                    f"Cleaning up partially imported model directory '{target_model_dir}' due to import failure."
                )
                try:
                    shutil.rmtree(target_model_dir)
                except OSError as e:
                    critical(
                        f"Failed to clean up partially imported model '{target_model_dir}': {e}"
                    )

    def export_model(
        self,
        model_name: str,
        output_filename: Union[str, Path] = DEFAULT_MODEL_EXPORT_FILENAME,
    ) -> None:
        """
        Exports a specific model directory to a .tar.gz archive.

        Args:
            model_name: The name of the model directory to export.
            output_filename: The name of the output .tar.gz file (e.g., "my_model.tar.gz").
        """
        self._check_permissions()

        source_model_dir = self.model_base_dir / model_name

        if not source_model_dir.is_dir():
            raise ModelManagerError(
                f"Source model directory '{source_model_dir}' does not exist or is not a directory. "
                "Nothing to export."
            )

        output_path = Path(output_filename).resolve()
        output_parent_dir = output_path.parent

        output_parent_dir.mkdir(parents=True, exist_ok=True)
        info(f"Ensured output directory exists: {output_parent_dir}")

        info(
            f"Compressing model '{model_name}' from '{source_model_dir}' to '{output_path}'..."
        )
        try:
            # Pass model_name as arcname_in_archive so the archive contains a top-level dir named model_name
            self.archive_manager.compress(
                source_model_dir, output_path, arcname_in_archive=model_name
            )

            info(f"Model '{model_name}' exported successfully to '{output_path}'!")
        except ArchiveManagerError as e:  # Catch specific exception from ArchiveManager
            raise ModelManagerError(f"Failed to export model: {e}")
        except Exception as e:
            raise ModelManagerError(
                f"An unexpected error occurred during model export: {e}"
            )

    def list_models(self) -> None:
        """Lists all models currently stored in the model base directory."""
        info(f"Listing models in '{self.model_base_dir}'...")

        if not self.model_base_dir.is_dir():
            info(
                f"Model base directory '{self.model_base_dir}' does not exist. No models found."
            )
            return

        models: List[str] = [
            d.name for d in self.model_base_dir.iterdir() if d.is_dir()
        ]

        if not models:
            info(f"No models found in '{self.model_base_dir}'.")
            return

        info("Available Models:")
        for m in sorted(models):
            info(f"  - {m}")
        info("Model listing complete.")

    def delete_model(self, model_name: str, force: bool = False) -> None:
        """
        Deletes a specific model directory.

        Args:
            model_name: The name of the model directory to delete.
            force: If True, delete without prompting for confirmation.
        """
        self._check_permissions()

        target_model_dir = self.model_base_dir / model_name

        if not target_model_dir.is_dir():
            raise ModelManagerError(
                f"Model directory '{target_model_dir}' does not exist or is not a directory. "
                "Nothing to delete."
            )

        if not force:
            warning(
                f"You are about to delete the model: '{target_model_dir}'. This action cannot be undone."
            )
            if not sys.stdin.isatty():
                raise ModelManagerError(
                    "Deleting model in non-interactive mode requires --force. "
                    "Please use 'delete <model_name> --force' or delete manually."
                )
            user_input = (
                input("Are you sure you want to proceed? (y/N): ").strip().lower()
            )
            if user_input != "y":
                info("Model deletion cancelled by user.")
                return

        info(f"Deleting model: '{target_model_dir}'...")
        try:
            shutil.rmtree(target_model_dir)
            info(
                f"Model '{model_name}' deleted successfully from '{self.model_base_dir}'."
            )
        except OSError as e:
            raise ModelManagerError(
                f"Failed to delete model '{target_model_dir}': {e}. "
                "Please check permissions or if the directory is in use."
            )
        except Exception as e:
            raise ModelManagerError(
                f"An unexpected error occurred during model deletion: {e}"
            )
