#!/usr/bin/env python3

import shutil
from pathlib import Path
from typing import Optional, Union, Any

from whl_deploy.utils.common import info, error, warning, critical
from whl_deploy.utils.common import ensure_dir
from whl_deploy.utils.file_loader import FileLoader, FileFetcherError
from whl_deploy.utils.archive_manager import ArchiveManager, ArchiveManagerError


class CacheManagerError(Exception):
    """Custom exception for CacheManager specific errors."""

    pass


# --- Configuration Constants ---
# Using Path object directly for consistency
BAZEL_CACHE_DIR = Path("/var/cache/bazel/repo_cache")
DEFAULT_CACHE_EXPORT_FILENAME = "bazel_repo_cache.tar.gz"

# --- Cache Manager Implementation ---


class CacheManager:
    """Manages Bazel repository cache (e.g., import, export, clear)."""

    def __init__(self, cache_dir: Path = BAZEL_CACHE_DIR):
        # Resolve path immediately to ensure it's absolute and consistent.
        # This self.cache_dir now primarily serves as the default for `clear_cache`
        # and `export_cache` if no input_path is provided.
        self.default_managed_cache_dir = cache_dir.resolve()
        self.file_loader = FileLoader()
        self.archive_manager = ArchiveManager()
        info(
            f"Initialized CacheManager with default managed directory: {self.default_managed_cache_dir}"
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
                             If False, raises CacheManagerError if target_dir is not empty.
        Raises:
            CacheManagerError: If target_dir is not empty and force_overwrite is False.
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
                raise CacheManagerError(
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
                raise CacheManagerError(
                    f"Failed to clean up existing content in '{target_dir}': {e}. "
                    "Please check permissions or if the directory is in use."
                )
        else:
            info(f"Target directory '{target_dir}' is empty. Proceeding.")

    def import_cache(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path] = BAZEL_CACHE_DIR,
        force_overwrite: bool = False,
    ) -> None:
        """
        Imports a Bazel cache archive from a local file or URL and extracts it
        to the specified output directory.

        Args:
            input_path: Path to the local archive file or URL of the archive.
            output_path: The directory where the cache will be extracted.
                         Defaults to BAZEL_CACHE_DIR.
            force_overwrite: If True, overwrite existing cache without requiring confirmation.
                             If False and output_path is not empty, will raise an error.
        """
        # Resolve output_path to a Path object for robust handling
        target_directory = Path(output_path).resolve().parent

        info(f"Preparing to import cache from '{input_path}' to '{target_directory}'.")

        ensure_dir(target_directory)

        local_archive_path: Optional[Path] = None
        try:
            # Fetch the archive (handles local files and URLs, temp downloads)
            # Ensure input_path is treated as a string for fetch method (if it expects str)
            local_archive_path = Path(self.file_loader.fetch(str(input_path)))

            info(
                f"Extracting cache archive '{local_archive_path}' to '{target_directory}'..."
            )

            # Use the ArchiveManager for decompression
            self.archive_manager.decompress(local_archive_path, target_directory)

            info("Cache imported and extracted successfully!")

        except FileFetcherError as e:
            raise CacheManagerError(
                f"Failed to fetch cache archive from '{input_path}': {e}"
            )
        except ArchiveManagerError as e:
            raise CacheManagerError(
                f"Failed to decompress cache archive '{local_archive_path}': {e}"
            )
        except OSError as e:
            raise CacheManagerError(
                f"File system error during cache import to '{target_directory}': {e}"
            )
        except Exception as e:
            critical(
                f"An unexpected error occurred during cache import: {e}", exc_info=True
            )
            raise CacheManagerError(
                f"An unexpected error occurred during cache import: {e}"
            )
        finally:
            # Ensure temporary files from FileLoader are cleaned up
            self.file_loader.cleanup_temp_files()

    def export_cache(
        self,
        input_path: Union[str, Path] = BAZEL_CACHE_DIR,
        output_path: str = DEFAULT_CACHE_EXPORT_FILENAME,
    ) -> None:
        """
        Exports a Bazel cache directory to a compressed archive.

        Args:
            input_path: The directory containing the cache to be exported.
                        Defaults to BAZEL_CACHE_DIR.
            output_path: The path and filename for the output archive (e.g., "/path/to/my_cache.tar.gz").
                         Defaults to DEFAULT_CACHE_EXPORT_FILENAME.
        """
        # Resolve input and output paths to Path objects for robust handling
        source_directory = Path(input_path).resolve()
        output_file_path = Path(output_path).resolve()

        info(
            f"Preparing to export cache from '{source_directory}' to '{output_file_path}'."
        )

        # Ensure the source directory for export exists and is accessible
        ensure_dir(source_directory)

        # Check if the source cache directory is empty
        if not source_directory.is_dir():
            raise CacheManagerError(
                f"Source cache directory '{source_directory}' does not exist or is not a directory. Nothing to export."
            )
        if not any(source_directory.iterdir()):
            warning(
                f"Cache directory '{source_directory}' is empty. Exporting an empty archive."
            )
            # Optionally, you might want to raise an error or exit here if empty exports are not desired.
            # For now, it will proceed to create an empty archive.

        # Ensure the parent directory for the output file exists
        ensure_dir(output_file_path.parent)

        try:
            info(
                f"Compressing cache from '{source_directory}' to '{output_file_path}'..."
            )
            self.archive_manager.compress(source_directory, output_file_path)
            info(f"Cache exported successfully to '{output_file_path}'!")
        except ArchiveManagerError as e:
            raise CacheManagerError(
                f"Failed to export cache from '{source_directory}' to '{output_file_path}': {e}"
            )
        except OSError as e:
            raise CacheManagerError(f"File system error during cache export: {e}")
        except Exception as e:
            critical(
                f"An unexpected error occurred during cache export: {e}", exc_info=True
            )
            raise CacheManagerError(
                f"An unexpected error occurred during cache export: {e}"
            )

    def clear_cache(self, force_clear: bool = False) -> None:
        """
        Clears the Bazel repository cache directory (self.default_managed_cache_dir).

        Args:
            force_clear: If True, clear cache without requiring confirmation.
                         If False and default_managed_cache_dir is not empty, will raise an error.
        """
        info(f"Preparing to clear cache at '{self.default_managed_cache_dir}'.")

        # Ensure the cache directory exists before trying to clear it
        ensure_dir(self.default_managed_cache_dir)

        if not any(self.default_managed_cache_dir.iterdir()):
            info(
                f"Cache directory '{self.default_managed_cache_dir}' is already empty. Nothing to clear."
            )
            return

        # If not empty and not forced, raise an error
        if not force_clear:
            raise CacheManagerError(
                f"Cache directory '{self.default_managed_cache_dir}' is not empty. "
                "Cannot proceed without --force (or equivalent) to clear existing content. "
                "Please run with --force."
            )

        try:
            info(f"Deleting all contents in '{self.default_managed_cache_dir}'...")
            shutil.rmtree(self.default_managed_cache_dir)

            # Re-create the directory after deletion to ensure it exists for future use
            ensure_dir(self.default_managed_cache_dir)
            info(f"Cache at '{self.default_managed_cache_dir}' cleared successfully!")
        except OSError as e:
            raise CacheManagerError(
                f"Failed to clear cache directory '{self.default_managed_cache_dir}': {e}. "
                "Please check permissions or if the directory is in use."
            )
        except Exception as e:
            critical(
                f"An unexpected error occurred during cache clear: {e}", exc_info=True
            )
            raise CacheManagerError(
                f"An unexpected error occurred during cache clear: {e}"
            )
