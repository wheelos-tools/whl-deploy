import os
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any

from whl_deploy.common import info, warning, error


class ArchiveManagerError(Exception):
    """Custom exception for ArchiveManager specific errors."""
    pass


class ArchiveManager:
    """
    Manages common archive operations (compress and decompress) for various formats.
    Currently supports .tar.gz, .zip archives.
    """

    def __init__(self):
        pass

    def decompress(self,
                   archive_path: Path,
                   destination_path: Path,
                   force_filter: Optional[str] = 'data',
                   target_top_level_dir_name: Optional[str] = None) -> None:
        """
        Decompresses an archive to a specified destination directory.
        Supports .tar.gz and .zip files.

        Args:
            archive_path: Path to the archive file to decompress.
            destination_path: Path to the directory where contents will be extracted.
            force_filter: Optional filter to apply during extraction for tar archives (e.g., 'data' for security).
                          Defaults to 'data' for tar archives (Python 3.8+). Not applicable for zip.
            target_top_level_dir_name: Optional new name for the *single* top-level directory found
                                       after decompression. If specified, the manager will attempt to
                                       identify a single top-level directory and rename it.
                                       If multiple top-level items or no single top-level directory are found,
                                       an ArchiveManagerError will be raised.
        Raises:
            ArchiveManagerError: If the archive is not valid, extraction fails, or automatic
                                 top-level directory renaming is not possible.
        """
        info(f"Decompressing '{archive_path}' to '{destination_path}'...")
        if not archive_path.is_file():
            raise ArchiveManagerError(
                f"Archive file not found: {archive_path}")

        # Ensure destination_path exists *before* extraction
        destination_path.mkdir(parents=True, exist_ok=True)

        # Record initial contents of destination_path (if any), to help identify newly extracted top-level dir.
        # This is a robust way to find what was newly added.
        initial_contents_names = set(
            p.name for p in destination_path.iterdir())

        if tarfile.is_tarfile(archive_path):
            self._decompress_tar(archive_path, destination_path, force_filter)
        elif zipfile.is_zipfile(archive_path):
            self._decompress_zip(archive_path, destination_path)
        else:
            raise ArchiveManagerError(
                f"'{archive_path.name}' is not a recognized archive format (.tar, .tar.gz, .zip, etc.)."
            )

        # Apply top-level directory renaming after successful decompression
        if target_top_level_dir_name:
            info(
                f"Attempting to rename top-level directory to '{target_top_level_dir_name}'...")

            # Identify the newly extracted top-level items
            extracted_top_level_items = [
                p for p in destination_path.iterdir() if p.name not in initial_contents_names]

            if not extracted_top_level_items:
                raise ArchiveManagerError(
                    f"No new content was extracted to '{destination_path}'. "
                    "Cannot perform top-level directory rename."
                )

            # Filter for directories among the newly extracted items
            extracted_top_level_dirs = [
                p for p in extracted_top_level_items if p.is_dir()]

            if len(extracted_top_level_dirs) == 1:
                source_path = extracted_top_level_dirs[0]
                old_name = source_path.name
                target_path = destination_path / target_top_level_dir_name

                # Check if the target_path already exists and is not the source_path
                if target_path.exists() and target_path != source_path:
                    raise ArchiveManagerError(
                        f"Target path '{target_path}' already exists and is different from source path '{source_path}'. "
                        "Cannot rename to an existing path."
                    )

                try:
                    info(
                        f"Renaming detected top-level directory '{old_name}' to '{target_top_level_dir_name}'...")
                    source_path.rename(target_path)
                    info("Top-level directory renaming completed successfully.")
                except OSError as e:
                    error(
                        f"Failed to rename '{source_path}' to '{target_path}': {e}")
                    raise ArchiveManagerError(
                        f"Failed to rename top-level directory: {e}")
            elif len(extracted_top_level_dirs) > 1:
                # This means the archive extracted multiple directories at the top level
                raise ArchiveManagerError(
                    f"Multiple top-level directories detected in '{destination_path}' after extraction: "
                    f"{[p.name for p in extracted_top_level_dirs]}. "
                    "Automatic single top-level directory renaming is not possible."
                )
            else:  # No directories, only files, or no new content that is a directory
                # Check if there are any new files at top level
                extracted_top_level_files = [
                    p for p in extracted_top_level_items if p.is_file()]
                if extracted_top_level_files:
                    raise ArchiveManagerError(
                        f"Archive extracted files directly to '{destination_path}' (e.g., {extracted_top_level_files[0].name}). "
                        "No single top-level directory was found to rename."
                    )
                else:  # Should not happen if extracted_top_level_items is not empty, but good for completeness
                    raise ArchiveManagerError(
                        f"Unexpected content structure in '{destination_path}'. "
                        "No single top-level directory was found to rename."
                    )

        info("Decompression completed successfully!")

    def _decompress_tar(self, archive_path: Path, destination_path: Path, force_filter: Optional[str]) -> None:
        """Internal helper for decompressing tar archives."""
        try:
            with tarfile.open(archive_path, "r:*") as tar:
                if force_filter and hasattr(tarfile, 'data_filter'):
                    tar.extractall(path=destination_path, filter=force_filter)
                elif force_filter:
                    warning(f"Python version does not support tarfile filter='{force_filter}'. "
                            "Proceeding without filter. Consider upgrading Python for security.")
                    tar.extractall(path=destination_path)
                else:
                    tar.extractall(path=destination_path)
        except tarfile.ReadError as e:
            raise ArchiveManagerError(
                f"Failed to read tar archive '{archive_path}': {e}. "
                "Is it corrupted or not a recognized tar compression?"
            )

    def _decompress_zip(self, archive_path: Path, destination_path: Path) -> None:
        """Internal helper for decompressing zip archives."""
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or any('..' == part for part in member_path.parts):
                        warning(
                            f"Skipping potentially malicious path in zip archive: {member.filename}")
                        continue
                    zf.extract(member, path=destination_path)
        except zipfile.BadZipFile as e:
            raise ArchiveManagerError(
                f"Failed to read zip archive '{archive_path}': {e}. Is it corrupted?")

    def compress(self, source_path: Path, output_path: Path, arcname_in_archive: Optional[str] = None) -> None:
        """
        Compresses a directory or file into an archive.
        Supports .tar, .tar.gz, .tar.bz2, and .zip formats based on output_path suffix.

        Args:
            source_path: Path to the directory or file to compress.
            output_path: Path to the output archive file.
            arcname_in_archive: Optional name to use for the source_path within the archive.
                                If None, the base name of source_path is used.
                                For directories, this often creates a single top-level directory in the archive.
        Raises:
            ArchiveManagerError: If compression fails.
        """
        info(f"Compressing '{source_path}' to '{output_path}'...")
        if not source_path.exists():
            raise ArchiveManagerError(f"Source path not found: {source_path}")

        # Ensure parent directory for output exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine compression mode based on file extension
        mode = None
        if output_path.suffix == '.zip':
            archive_type = 'zip'
        elif output_path.suffix == '.gz' and output_path.stem.endswith('.tar'):
            archive_type = 'tar'
            mode = "w:gz"
        elif output_path.suffix == '.bz2' and output_path.stem.endswith('.tar'):
            archive_type = 'tar'
            mode = "w:bz2"
        elif output_path.suffix == '.tar':
            archive_type = 'tar'
            mode = "w"
        else:
            # Default to .tar.gz if suffix is not recognized
            warning(f"Unsupported output archive format suffix for '{output_path.name}'. "
                    f"Defaulting to '.tar.gz'.")
            output_path = output_path.with_suffix(
                '').with_suffix('.tar').with_suffix('.gz')
            archive_type = 'tar'
            mode = "w:gz"

        try:
            if archive_type == 'zip':
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    if source_path.is_dir():
                        for root, _, files in os.walk(source_path):
                            for file in files:
                                file_path = Path(root) / file
                                # Calculate arcname relative to source_path
                                # If arcname_in_archive is provided, prepend it
                                rel_path = file_path.relative_to(source_path)
                                final_arcname = Path(
                                    arcname_in_archive or source_path.name) / rel_path
                                zf.write(file_path, arcname=str(final_arcname))
                    else:  # Single file
                        final_arcname = Path(
                            arcname_in_archive or source_path.name)
                        zf.write(source_path, arcname=str(final_arcname))

            elif archive_type == 'tar':
                with tarfile.open(output_path, mode) as tar:
                    # tar.add handles both files and directories recursively.
                    # arcname parameter controls the name inside the archive.
                    # This creates a single top-level directory in the archive.
                    tar.add(source_path,
                            arcname=arcname_in_archive or source_path.name)

            info("Compression completed successfully!")
        except Exception as e:
            raise ArchiveManagerError(
                f"Failed to compress '{source_path}': {e}")
