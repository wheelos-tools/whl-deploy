import os
import stat
import tarfile
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from whl_deploy.utils.common import debug, info, warning, error


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

    def decompress(
        self,
        archive_path: Path,
        destination_path: Path,
        force_filter: Optional[str] = None,
        prefix_to_remove: Optional[Path] = None,
        target_top_level_dir_name: Optional[str] = None,
    ) -> None:
        """
        Decompresses an archive to a specified destination directory.
        Supports .tar.gz and .zip files.

        Args:
            archive_path: Path to the archive file to decompress.
            destination_path: Path to the directory where contents will be extracted.
            force_filter: Optional filter to apply during extraction for tar archives.
            target_top_level_dir_name: Optional new name for the *single* top-level directory found
                                      after decompression.
            prefix_to_remove: If specified, this prefix will be removed from the
                              paths of extracted contents.

        Raises:
            ArchiveManagerError: If the archive is not valid, extraction fails,
                                or automatic renaming of the directory is not possible.
        """
        info(f"Decompressing '{archive_path}' to '{destination_path}'...")
        destination_path.mkdir(parents=True, exist_ok=True)

        if archive_path.is_dir():
            info(f"Archive path '{archive_path}' is a directory -- using direct copy mode")
            try:
                shutil.copytree(archive_path, destination_path, dirs_exist_ok=True, symlinks=True)
            except Exception as e:
                raise ArchiveManagerError(f"Failed to copy directory '{archive_path}' to '{destination_path}': {e}")
        elif not archive_path.is_file():
            raise ArchiveManagerError(f"Archive file not found: {archive_path}")
        else:
            # Ensure the destination directory exists
            destination_path.mkdir(parents=True, exist_ok=True)

            initial_contents_names = set(p.name for p in destination_path.iterdir())

            if tarfile.is_tarfile(archive_path):
                self._decompress_tar(archive_path, destination_path, force_filter, prefix_to_remove)
            elif zipfile.is_zipfile(archive_path):
                self._decompress_zip(archive_path, destination_path, prefix_to_remove)
            else:
                raise ArchiveManagerError(f"'{archive_path.name}' is not a recognized archive format.")

            # Handle top-level directory renaming if specified
            if target_top_level_dir_name:
                self._rename_top_level_directory(destination_path, initial_contents_names, target_top_level_dir_name, prefix_to_remove)

        info("Decompression completed successfully!")

    def _decompress_tar(self, archive_path: Path, destination_path: Path, force_filter: Optional[str], prefix_to_remove: Optional[Path]) -> None:
        """Decompress a tar file, handling prefix removal."""
        debug(f"Extracting: {archive_path} to {destination_path}")

        with tarfile.open(archive_path, "r") as tar:
            for member in tar.getmembers():
                # Check if we should apply the force_filter
                if force_filter and force_filter not in member.name:
                    debug(f"Skipping: {member.name} due to filter")
                    continue  # Skip this member if it does not match the filter

                # Determine the arcname and the destination to remove the specified prefix if provided
                member_path = Path(member.name)
                if prefix_to_remove:
                    # Calculate arcname by removing the prefix
                    arcname = member_path.relative_to(prefix_to_remove) if member_path.is_relative_to(prefix_to_remove) else member_path
                else:
                    arcname = member_path

                # Full extraction path
                full_path = destination_path / arcname

                # Create directories if they don't exist
                if not full_path.parent.exists():
                    full_path.parent.mkdir(parents=True, exist_ok=True)

                debug(f"Extracting: {member.name} to {full_path}")

                try:
                    if member.issym() or member.islnk():
                        tar.extract(member, path=destination_path)  # Extract symlinks and hard links
                    else:
                        tar.extract(member, path=destination_path)

                    # Optionally move to correct path if needed
                    if arcname != member_path and (destination_path / member.name).exists():
                        debug(f"Moving extracted file from {destination_path / member.name} to {full_path}")
                        shutil.move(destination_path / member.name, full_path)

                except Exception as e:
                    print(f"Error extracting {member.name}: {str(e)}")

    def _decompress_zip(self, archive_path: Path, destination_path: Path, prefix_to_remove: Optional[Path]) -> None:
        """Decompress a zip file, handling prefix removal."""
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                # Determine the arcname by removing the prefix if provided
                member_path = Path(member)
                if prefix_to_remove:
                    arcname = member_path.relative_to(prefix_to_remove) if member_path.is_relative_to(prefix_to_remove) else member_path
                else:
                    arcname = member_path

                zip_ref.extract(member, destination_path)
                # Rename extracted file or directory to the correct path
                if arcname != member_path:
                    shutil.move(destination_path / member, destination_path / arcname)

    def _rename_top_level_directory(
        self,
        destination_path: Path,
        initial_contents_names: set,
        target_top_level_dir_name: str,
        prefix_to_remove: Optional[Path]
    ) -> None:
        """Renames the top-level directory in the destination path if possible."""
        extracted_top_level_items = [
            p for p in destination_path.iterdir() if p.name not in initial_contents_names
        ]

        if not extracted_top_level_items:
            raise ArchiveManagerError("No new content was extracted. Cannot perform top-level directory rename.")

        # Filter directories
        extracted_top_level_dirs = [p for p in extracted_top_level_items if p.is_dir()]

        if len(extracted_top_level_dirs) == 1:
            source_path = extracted_top_level_dirs[0]
            target_path = destination_path / target_top_level_dir_name

            if target_path.exists() and target_path != source_path:
                raise ArchiveManagerError(f"Target path '{target_path}' already exists and cannot be renamed.")

            try:
                info(f"Renaming directory '{source_path.name}' to '{target_top_level_dir_name}'...")
                source_path.rename(target_path)
                info("Top-level directory renamed successfully.")
            except OSError as e:
                raise ArchiveManagerError(f"Failed to rename '{source_path}' to '{target_path}': {e}")

        elif len(extracted_top_level_dirs) > 1:
            raise ArchiveManagerError("Multiple top-level directories detected. Unable to rename.")
        else:
            raise ArchiveManagerError("No single top-level directory found to rename.")

    def compress(
        self,
        source_path: Path,
        output_path: Path,
        prefix_to_remove: Optional[Path] = None,
        arcname_in_archive: Optional[str] = None,
    ) -> None:
        """
        Compresses a directory or file into an archive.
        Supports .tar, .tar.gz, .tar.bz2, and .zip formats based on output_path suffix.

        Args:
            source_path: Path to the directory or file to compress.
            output_path: Path to the output archive file.
            prefix_to_remove: If specified, this prefix will be removed from the
                              source_path when stored in the archive.
            arcname_in_archive: Optional name to use for the source_path within the archive.
                                If None, the base name of source_path is used.

        Raises:
            ArchiveManagerError: If compression fails.
        """
        info(f"Compressing '{source_path}' to '{output_path}', prefix remove :{prefix_to_remove}...")
        if not source_path.exists():
            raise ArchiveManagerError(f"Source path not found: {source_path}")

        # Ensure parent directory for output exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine compression mode based on file extension
        mode = None
        if output_path.suffix == ".zip":
            archive_type = "zip"
        elif output_path.suffix == ".gz" and output_path.stem.endswith(".tar"):
            archive_type = "tar"
            mode = "w:gz"
        elif output_path.suffix == ".bz2" and output_path.stem.endswith(".tar"):
            archive_type = "tar"
            mode = "w:bz2"
        elif output_path.suffix == ".tar":
            archive_type = "tar"
            mode = "w"
        else:
            # Default to .tar.gz if suffix is not recognized
            warning(
                f"Unsupported output archive format suffix for '{output_path.name}'. "
                f"Defaulting to '.tar.gz'."
            )
            output_path = output_path.with_suffix(".tar.gz")
            archive_type = "tar"
            mode = "w:gz"

        try:
            if archive_type == "zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    if source_path.is_dir():
                        for root, _, files in os.walk(source_path):
                            for file in files:
                                file_path = Path(root) / file
                                # Calculate arcname relative to source_path, removing prefix
                                if prefix_to_remove:
                                    rel_path = file_path.relative_to(prefix_to_remove)
                                else:
                                    rel_path = file_path.relative_to(source_path)

                                final_arcname = (
                                    Path(arcname_in_archive or source_path.name) / rel_path
                                )
                                zf.write(file_path, arcname=str(final_arcname))

                    else:  # Single file
                        final_arcname = Path(arcname_in_archive or source_path.name)
                        zf.write(source_path, arcname=str(final_arcname))

            elif archive_type == "tar":
                with tarfile.open(output_path, mode) as tar:
                    # Add items to the tar archive, removing prefix if specified
                    if source_path.is_dir():
                        for item in os.listdir(source_path):
                            item_path = source_path / item
                            if prefix_to_remove:
                                arcname = item_path.relative_to(prefix_to_remove)
                            else:
                                arcname = item_path.relative_to(source_path)

                            tar.add(item_path, arcname=arcname)
                    else:  # Single file
                        arcname = source_path.relative_to(prefix_to_remove) if prefix_to_remove else source_path.name
                        tar.add(source_path, arcname=arcname)

        except Exception as e:
            raise ArchiveManagerError(f"Compression failed: {e}")
