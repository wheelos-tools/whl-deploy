#!/usr/bin/env python3

import sys
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from whl_deploy.common import (
    info, warning, error, critical
)
from whl_deploy.file_loader import FileLoader, FileFetcherError
from whl_deploy.archive_manager import ArchiveManager, ArchiveManagerError


class CacheManagerError(Exception):
    """Custom exception for CacheManager specific errors."""
    pass


# --- Configuration Constants ---
BAZEL_CACHE_DIR = Path("/var/cache/bazel/repo_cache")
DEFAULT_CACHE_EXPORT_FILENAME = "bazel_repo_cache.tar.gz"

# --- Cache Manager Implementation ---


class CacheManager:
    """Manages Bazel repository cache (e.g., import, export, clear)."""

    def __init__(self, cache_dir: Path = BAZEL_CACHE_DIR):
        self.cache_dir = cache_dir.resolve()
        self.file_loader = FileLoader()
        self.archive_manager = ArchiveManager() # Initialize the new archive manager
        info(f"Initialized CacheManager for directory: {self.cache_dir}")

    def _ensure_cache_dir_prepared(self) -> None:
        """
        Ensures the cache directory exists and has appropriate permissions.
        This method is idempotent.
        """
        info(
            f"Ensuring cache directory '{self.cache_dir}' exists and has correct permissions...")
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Use 0o775 for directory: rwx for owner/group, r-x for others.
            # This is commonly used for shared directories like cache,
            # where Bazel might be run by different users within a group.
            # chmod(mode) applies permissions.
            self.cache_dir.chmod(0o775)
            info(
                f"Cache directory '{self.cache_dir}' is prepared with permissions 0775.")
        except OSError as e:
            # Raise CacheManagerError for consistency with other methods
            raise CacheManagerError(
                f"Failed to prepare cache directory '{self.cache_dir}': {e}. "
                "Please check permissions for path or parent directories."
            )

    def import_cache(self, source_path: str, force_overwrite: bool = False) -> None:
        """
        Imports a Bazel cache archive from a local file or URL and extracts it.
        This will overwrite any existing contents in the cache directory,
        optionally after user confirmation.

        Args:
            source_path: Path to the local archive file or URL of the archive.
            force_overwrite: If True, overwrite existing cache without asking.
                             If False, prompt the user for confirmation if the directory is not empty.
        """
        info(
            f"Preparing to import cache from '{source_path}' to '{self.cache_dir}'.")
        # Ensure cache_dir exists before checking its contents or attempting cleanup
        self._ensure_cache_dir_prepared()

        # Check if cache_dir is not empty and requires confirmation
        cache_dir_is_not_empty = any(self.cache_dir.iterdir())
        if cache_dir_is_not_empty:
            if not force_overwrite:
                warning(f"Existing cache found in '{self.cache_dir}'.")
                # Logical error: Check for TTY before asking for input, not after
                if not sys.stdin.isatty():
                    raise CacheManagerError(
                        "Existing cache found and running in non-interactive mode. "
                        "Use --force to overwrite or clear manually."
                    )
                user_input = input(
                    "This operation will delete all existing contents. Continue? (y/N): "
                ).strip().lower()
                if user_input != 'y':
                    info("Operation cancelled by user.")
                    return  # Exit without doing anything
            else:
                info("Force overwrite enabled. Proceeding to delete existing cache.")
        else:
            info(
                f"Cache directory '{self.cache_dir}' is empty. Proceeding with import.")

        # Step 1: Clean up existing cache directory contents for a fresh import.
        # It's safer to remove and re-create for idempotency and to avoid leftovers.
        # Logical error: If self.cache_dir does not exist, shutil.rmtree will fail.
        # _ensure_cache_dir_prepared() ensures it exists, so this check is for contents.
        # If cache_dir_is_not_empty is True, it means cache_dir exists and has content.
        # If force_overwrite or user confirmed, then delete.
        if cache_dir_is_not_empty and (force_overwrite or user_input == 'y'): # Ensure we only delete if confirmed/forced
            try:
                info(f"Cleaning up existing cache directory: {self.cache_dir}")
                shutil.rmtree(self.cache_dir)
                info(
                    f"Successfully deleted old cache from '{self.cache_dir}'.")
            except OSError as e:
                raise CacheManagerError(
                    f"Failed to clean up existing cache in '{self.cache_dir}': {e}. "
                    "Please check permissions or if the directory is in use."
                )

        # Re-prepare the directory to ensure it's empty and has correct permissions for extraction
        self._ensure_cache_dir_prepared()

        local_archive_path: Optional[Path] = None
        try:
            local_archive_path = Path(self.file_loader.fetch(source_path))

            # Use the new ArchiveManager for decompression
            self.archive_manager.decompress(local_archive_path, self.cache_dir) # <--- Using ArchiveManager

            info("Cache imported and extracted successfully!")

        except FileFetcherError as e:
            raise CacheManagerError(f"Failed to fetch cache archive: {e}")
        except ArchiveManagerError as e: # Catch ArchiveManager's specific exception
            raise CacheManagerError(f"Failed to decompress cache archive: {e}")
        except Exception as e:
            raise CacheManagerError(
                f"An unexpected error occurred during import from '{source_path}' or decompression: {e}" # Adjusted message
            )
        finally:
            self.file_loader.cleanup_temp_files()

    def export_cache(self, output_filename: str = DEFAULT_CACHE_EXPORT_FILENAME) -> None:
        """
        Exports the current Bazel cache directory to a compressed archive.

        Args:
            output_filename: The name of the output archive file (e.g., "my_cache.tar.gz").
        """
        self._ensure_cache_dir_prepared()

        # Logical error: `any(self.cache_dir.iterdir())` will raise StopIteration if directory is empty.
        # This is not a logical error in the sense of crashing, but it's not the most robust way to check.
        # A simpler way to check if a directory is empty.
        is_cache_dir_empty = not any(self.cache_dir.iterdir()) # Corrected check

        if is_cache_dir_empty:
            warning(
                f"Cache directory '{self.cache_dir}' is empty. Nothing to export.")
            return

        # Convert output_filename to Path and resolve to absolute path
        output_path = Path(output_filename).resolve()

        # Use the new ArchiveManager for compression
        try:
            self.archive_manager.compress(self.cache_dir, output_path) # <--- Using ArchiveManager
        except ArchiveManagerError as e: # Catch ArchiveManager's specific exception
            raise CacheManagerError(f"Failed to export cache: {e}")
        except Exception as e:
            raise CacheManagerError(
                f"An unexpected error occurred during cache export: {e}"
            )

    def clear_cache(self) -> None:
        """
        Clears the Bazel repository cache directory.
        Prompts for confirmation unless --force is used (assumed handled by CLI).
        """
        info(f"Preparing to clear cache at '{self.cache_dir}'.")
        self._ensure_cache_dir_prepared()

        # Logical error: `any(self.cache_dir.iterdir())` will raise StopIteration if directory is empty.
        # Use a more robust check for empty directory.
        is_cache_dir_empty = not any(self.cache_dir.iterdir()) # Corrected check

        if is_cache_dir_empty:
            info(
                f"Cache directory '{self.cache_dir}' is already empty. Nothing to clear.")
            return

        # Logical error: force_overwrite check is missing here, and it's assumed by CLI.
        # The prompt should be conditional on whether force_overwrite is true or not.
        # If the CLI is always providing --force for non-interactive clear, then this is fine.
        # If not, this needs 'force_clear' parameter. Assuming for now CLI handles it, so always prompt if not empty.
        if not sys.stdin.isatty():
            # If `force_clear` parameter was added to clear_cache, it would be checked here.
            # For now, it's a hard error if not interactive.
            raise CacheManagerError(
                "Clearing cache in non-interactive mode. "
                "This operation requires explicit confirmation or a '--force' flag (if implemented). "
                "Please run interactively or adjust the script's call."
            )

        user_input = input(
            f"Are you sure you want to delete all contents in '{self.cache_dir}'? (y/N): "
        ).strip().lower()

        if user_input != 'y':
            info("Cache clear operation cancelled by user.")
            return

        try:
            info(f"Deleting all contents in '{self.cache_dir}'...")
            shutil.rmtree(self.cache_dir)
            self._ensure_cache_dir_prepared()
            info(f"Cache at '{self.cache_dir}' cleared successfully!")
        except OSError as e:
            raise CacheManagerError(
                f"Failed to clear cache directory '{self.cache_dir}': {e}. "
                "Please check permissions or if the directory is in use."
            )
        except Exception as e:
            raise CacheManagerError(
                f"An unexpected error occurred during cache clear: {e}")
