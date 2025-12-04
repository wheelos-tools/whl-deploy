# Copyright 2025 The WheelOS Team. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Created Date: 2025-11-30
# Author: daohu527@gmail.com



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

    def is_archive(self, archive_path):
        return tarfile.is_tarfile(archive_path) or zipfile.is_zipfile(archive_path)

    def decompress(
        self,
        archive_path: Path,
        destination_path: Path,
        force_filter: Optional[str] = None,
        target_top_level_dir_name: Optional[str] = None,
    ) -> None:
        """
        Decompress an archive or copy a directory to destination.
        Automatically removes the archive's top-level directory if present.
        Preserves executable permissions.
        """
        info(f"Decompressing '{archive_path}' to '{destination_path}'...")
        destination_path.mkdir(parents=True, exist_ok=True)

        # Final target directory
        if target_top_level_dir_name:
            final_destination = destination_path / target_top_level_dir_name
            final_destination.mkdir(parents=True, exist_ok=True)
        else:
            final_destination = destination_path

        # Custom copy function, retaining user-executable permissions.
        def copy_with_user_exec(src, dst):
            shutil.copy2(src, dst)
            st = os.stat(dst)
            os.chmod(dst, st.st_mode | stat.S_IXUSR)

        if archive_path.is_dir():
            # Copy the directory directly
            try:
                shutil.copytree(
                    archive_path,
                    final_destination,
                    dirs_exist_ok=True,
                    symlinks=True,
                    copy_function=copy_with_user_exec,
                )
            except Exception as e:
                raise ArchiveManagerError(
                    f"Failed to copy directory '{archive_path}': {e}")
        elif archive_path.is_file():
            prefix_to_remove = None

            if tarfile.is_tarfile(archive_path):
                # Automatically detect top-level directory
                with tarfile.open(archive_path, "r") as tar:
                    top_level_dirs = {
                        Path(m.name).parts[0]
                        for m in tar.getmembers() if m.name.strip()
                    }
                    if len(top_level_dirs) == 1:
                        prefix_to_remove = Path(top_level_dirs.pop())
                self._decompress_tar(archive_path, final_destination,
                                     force_filter, prefix_to_remove)
            elif zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    top_level_dirs = {
                        Path(m).parts[0]
                        for m in zip_ref.namelist() if m.strip()
                    }
                    if len(top_level_dirs) == 1:
                        prefix_to_remove = Path(top_level_dirs.pop())
                self._decompress_zip(archive_path, final_destination,
                                     prefix_to_remove)
            else:
                raise ArchiveManagerError(
                    f"Unsupported archive format: {archive_path}")
        else:
            raise ArchiveManagerError(f"Archive not found: {archive_path}")

        print("Decompression completed successfully!")

    def _decompress_tar(
        self,
        archive_path: Path,
        destination_path: Path,
        force_filter: Optional[str],
        prefix_to_remove: Optional[Path],
    ) -> None:
        with tarfile.open(archive_path, "r") as tar:
            for member in tar.getmembers():
                if force_filter and force_filter not in member.name:
                    continue
                member_path = Path(member.name)
                if prefix_to_remove:
                    try:
                        arcname = member_path.relative_to(prefix_to_remove)
                    except ValueError:
                        arcname = member_path
                else:
                    arcname = member_path
                full_path = destination_path / arcname
                if member.isdir():
                    full_path.mkdir(parents=True, exist_ok=True)
                else:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    tar.extract(member, path=destination_path)
                    extracted_path = destination_path / member.name
                    if extracted_path != full_path:
                        shutil.move(str(extracted_path), str(full_path))
                    if full_path.is_file():
                        st = os.stat(full_path)
                        os.chmod(full_path, st.st_mode | stat.S_IXUSR)

    def _decompress_zip(
        self,
        archive_path: Path,
        destination_path: Path,
        prefix_to_remove: Optional[Path],
    ) -> None:
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or any(
                            '..' == part for part in member_path.parts):
                        warning(
                            f"Skipping potentially malicious path in zip archive: {member.filename}"
                        )
                        continue
                    if prefix_to_remove:
                        try:
                            arcname = member_path.relative_to(prefix_to_remove)
                        except ValueError:
                            arcname = member_path
                    else:
                        arcname = member_path
                    full_path = destination_path / arcname
                    if member.filename.endswith("/"):
                        full_path.mkdir(parents=True, exist_ok=True)
                    else:
                        full_path.parent.mkdir(parents=True, exist_ok=True)

                        attr = member.external_attr >> 16
                        if attr & stat.S_IFLNK == stat.S_IFLNK:
                            # Handle symbolic links
                            link_target = zf.read(
                                member.filename).decode('utf-8')
                            os.symlink(link_target, full_path)
                            continue

                        # regular file
                        member.filename = full_path.as_posix()
                        extracted_path = zf.extract(member,
                                                    path=destination_path)
                        if extracted_path != full_path:
                            shutil.move(str(extracted_path), str(full_path))

                        # Extract the permission bits (last 9 bits of external_attr >> 16)
                        # and apply them with os.chmod
                        mode = attr & 0o777
                        if mode:
                            try:
                                os.chmod(full_path, mode)
                            except OSError as e:
                                warning(r'Could not set permissions for'
                                        f' {full_path}: {e}')
        except zipfile.BadZipFile as e:
            raise ArchiveManagerError(
                f"Failed to read zip archive '{archive_path}': {e}. Is it corrupted?"
            )

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
        info(
            f"Compressing '{source_path}' to '{output_path}', prefix remove :{prefix_to_remove}..."
        )
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
        elif output_path.suffix == ".bz2" and output_path.stem.endswith(
                ".tar"):
            archive_type = "tar"
            mode = "w:bz2"
        elif output_path.suffix == ".tar":
            archive_type = "tar"
            mode = "w"
        else:
            # Default to .tar.gz if suffix is not recognized
            warning(
                f"Unsupported output archive format suffix for '{output_path.name}'. "
                f"Defaulting to '.tar.gz'.")
            output_path = output_path.with_suffix(".tar.gz")
            archive_type = "tar"
            mode = "w:gz"

        try:
            if archive_type == "zip":
                with zipfile.ZipFile(output_path, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    if source_path.is_dir():
                        for root, _, files in os.walk(source_path):
                            for file in files:
                                file_path = Path(root) / file
                                # Calculate arcname relative to source_path, removing prefix
                                if prefix_to_remove:
                                    rel_path = file_path.relative_to(
                                        prefix_to_remove)
                                else:
                                    rel_path = file_path.relative_to(
                                        source_path)

                                final_arcname = (Path(arcname_in_archive
                                                      or source_path.name) /
                                                 rel_path)
                                zf.write(file_path, arcname=str(final_arcname))

                    else:  # Single file
                        final_arcname = Path(arcname_in_archive
                                             or source_path.name)
                        zf.write(source_path, arcname=str(final_arcname))

            elif archive_type == "tar":
                with tarfile.open(output_path, mode) as tar:
                    # Add items to the tar archive, removing prefix if specified
                    if source_path.is_dir():
                        for item in os.listdir(source_path):
                            item_path = source_path / item
                            if prefix_to_remove:
                                arcname = item_path.relative_to(
                                    prefix_to_remove)
                            else:
                                arcname = item_path.relative_to(source_path)

                            tar.add(item_path, arcname=arcname)
                    else:  # Single file
                        arcname = (source_path.relative_to(prefix_to_remove)
                                   if prefix_to_remove else source_path.name)
                        tar.add(source_path, arcname=arcname)

        except Exception as e:
            raise ArchiveManagerError(f"Compression failed: {e}")
