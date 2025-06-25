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

    def decompress(self, archive_path: Path, destination_path: Path, force_filter: Optional[str] = 'data') -> None:
        """
        Decompresses an archive to a specified destination directory.
        Supports .tar.gz and .zip files.

        Args:
            archive_path: Path to the archive file to decompress.
            destination_path: Path to the directory where contents will be extracted.
            force_filter: Optional filter to apply during extraction for tar archives (e.g., 'data' for security).
                          Defaults to 'data' for tar archives (Python 3.8+). Not applicable for zip.
        Raises:
            ArchiveManagerError: If the archive is not valid or extraction fails.
        """
        info(f"Decompressing '{archive_path}' to '{destination_path}'...")
        if not archive_path.is_file():
            raise ArchiveManagerError(
                f"Archive file not found: {archive_path}")

        destination_path.mkdir(parents=True, exist_ok=True)

        if tarfile.is_tarfile(archive_path):
            try:
                # Use r:* to auto-detect compression
                with tarfile.open(archive_path, "r:*") as tar:
                    # Check if filter feature exists (Python 3.8+)
                    if force_filter and hasattr(tarfile, 'data_filter'):
                        tar.extractall(path=destination_path,
                                       filter=force_filter)
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
        elif zipfile.is_zipfile(archive_path):
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # Manual path traversal check for zipfile as it lacks filter parameter in older Python versions
                    # This check makes the zip extraction safer.
                    for member in zf.infolist():
                        # Path.parts handles path components robustly
                        normalized_parts = Path(member.filename).parts
                        if any(part == '..' for part in normalized_parts) or Path(member.filename).is_absolute():
                            warning(
                                f"Skipping potentially malicious path in zip archive: {member.filename}")
                            continue
                        # Use extract rather than extractall for member-by-member control
                        # member.filename might contain internal directories which extract handles
                        zf.extract(member, path=destination_path)
            except zipfile.BadZipFile as e:
                raise ArchiveManagerError(
                    f"Failed to read zip archive '{archive_path}': {e}. Is it corrupted?")
        else:
            raise ArchiveManagerError(
                f"'{archive_path.name}' is not a recognized archive format (.tar, .tar.gz, .zip, etc.)."
            )

        info("Decompression completed successfully!")

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
