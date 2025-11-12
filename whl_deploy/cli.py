#!/usr/bin/env python3

import sys
import argparse
import tarfile
import shutil
from typing import Optional, Any, Callable, Union
from pathlib import Path
import os


from whl_deploy.common import info, error, warning, critical, ManagerError
from whl_deploy.prompt import print_help
from whl_deploy.ip_country_checker import can_access_github
from whl_deploy.prepare.install_docker import DockerManager
from whl_deploy.prepare.install_nvidia_container_toolkit import NvidiaToolkitManager
from whl_deploy.prepare.config_system import HostConfigManager
from whl_deploy.resource.cache import (
    DEFAULT_CACHE_EXPORT_FILENAME,
    CacheManager,
    BAZEL_CACHE_DIR,
)
from whl_deploy.resource.docker_image import (
    DockerImageManager,
    DEFAULT_IMAGE_NAME,
    DEFAULT_IMAGE_EXPORT_FILENAME,
)
from whl_deploy.resource.maps import (
    MapManager,
    DEFAULT_MAP_IMPORT_DIR,
    DEFAULT_MAP_EXPORT_FILENAME,
)
from whl_deploy.resource.models import (
    ModelManager,
    DEFAULT_MODEL_IMPORT_DIR,
    DEFAULT_MODEL_EXPORT_FILENAME,
)
from whl_deploy.resource.source_code import (
    SourcePackageManager,
    DEFAULT_SOURCE_DIR,
    DEFAULT_SOURCE_EXPORT_FILENAME,
)

# --- Custom Exceptions ---


class OrchestratorError(Exception):
    """Custom exception for errors during orchestration processes."""

    pass


def prompt_for_confirmation(prompt_text: str, auto_confirm: bool) -> bool:
    """
    A unified prompt function.
    Args:
        prompt_text: The question to ask the user.
        auto_confirm: If True, automatically returns True without prompting the user.

    Returns:
        True if the user confirms or if auto_confirm is True, False otherwise.
    """
    if auto_confirm:
        info(f"'{prompt_text}'... proceeding automatically.")
        return True

    while True:
        try:
            user_input = input(f"❓ {prompt_text}? [Y/n]: ").strip().lower()
            if user_input in ["y", "yes", ""]:
                return True
            elif user_input in ["n", "no"]:
                warning(f"Skipping step: {prompt_text}")
                return False
            else:
                warning("Invalid input. Please enter 'y' or 'n'.")
        except KeyboardInterrupt:
            warning("\nOperation interrupted by user.")
            raise


# --- Orchestrator Class ---


class HostSetupOrchestrator:
    """
    Orchestrates the setup of the host environment and the import/export of data.
    """

    def __init__(self, mirror_region: Optional[str] = None):
        info("Initializing Host Setup Orchestrator...")
        self.mirror_region = mirror_region
        self.docker_manager = DockerManager(mirror_region=self.mirror_region)
        self.nvidia_toolkit_manager = NvidiaToolkitManager(
            mirror_region=self.mirror_region
        )
        self.host_config_manager = HostConfigManager()
        self.cache_manager = CacheManager()
        self.docker_image_manager = DockerImageManager()
        self.map_manager = MapManager()
        self.model_manager = ModelManager()
        self.source_package_manager = SourcePackageManager()
        # Define default sub-directory names within a combined package
        self.PACKAGE_SUBDIRS = {
            "source_code": "source_code",
            # This sub-directory will contain the .tar image file(s)
            "docker_image": "docker_image",
            "maps": "maps",
            "models": "models",
            "cache": "cache",
        }

    # --- Composite Interactive Flows ---
    def setup_all(self, non_interactive: bool = False, uninstall: bool = False) -> None:
        """
        Runs the full environment setup process, with interactive prompts for each step.
        """
        action_word = "Uninstalling" if uninstall else "Setting up"
        info(f"--- 🚀 Starting Full Environment {action_word.split(' ')[0]} ---")

        if prompt_for_confirmation(f"{action_word} Docker", True):
            self.setup_docker(uninstall)

        if prompt_for_confirmation(
            f"{action_word} NVIDIA Container Toolkit", non_interactive
        ):
            self.setup_nvidia_toolkit(uninstall)

        if not uninstall and prompt_for_confirmation(
            "Configure Host System", non_interactive
        ):
            self.setup_host_config()

        info(f"--- 🎉 Full Environment {action_word.split(' ')[0]} Complete ---")

    def import_all(
        self,
        package_path: str,
        non_interactive_global: bool = False,
        confirm_source_code: bool = True,
        confirm_docker_image: bool = True,
        confirm_maps: bool = True,
        confirm_models: bool = True,
        confirm_cache: bool = True,
    ) -> None:
        """
        Runs the full data import process from a single package file,
        with interactive prompts for each resource. Global non_interactive_global
        flag or individual confirm_xxx flags control prompting.
        """
        info("--- 🚀 Starting Full Data Import from Package ---")
        package_path_obj = Path(package_path)
        if not package_path_obj.exists():
            raise OrchestratorError(f"Import package not found: {package_path}")

        temp_extract_dir = (
            package_path_obj.parent / f"{package_path_obj.stem}_extracted"
        )
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        info(
            f"Extracting package '{package_path}' to temporary directory '{temp_extract_dir}'..."
        )

        try:
            with tarfile.open(package_path, "r") as tar:
                tar.extractall(path=temp_extract_dir)
            info("Package extracted successfully.")

            extracted_contents = list(temp_extract_dir.iterdir())
            # Debug print
            print(f"Extracted contents in temp root: {extracted_contents}")
            if not extracted_contents:
                raise OrchestratorError("Extracted package is empty.")
            # Determine the actual root directory of the extracted package
            # This is important if the tarball itself contains a single top-level directory.
            package_root_dir = (
                extracted_contents[0]
                if len(extracted_contents) == 1 and extracted_contents[0].is_dir()
                else temp_extract_dir
            )
            # Debug print
            print(f"Package root directory assumed to be: {package_root_dir}")

            force_individual_import_overwrite = True

            # Import Source Code
            auto_confirm_src = non_interactive_global or (not confirm_source_code)
            if prompt_for_confirmation("Import source code", auto_confirm_src):
                # Construct path to the subdirectory within the package
                src_subdir = package_root_dir / self.PACKAGE_SUBDIRS["source_code"]
                # Then construct path to the .tar file within that subdirectory
                src_file_path = src_subdir / DEFAULT_SOURCE_EXPORT_FILENAME
                # Debug print
                print(f"Looking for source code at: {src_file_path}")
                if src_file_path.exists():
                    self.import_source_code(
                        str(src_file_path),
                        force_overwrite=force_individual_import_overwrite,
                    )
                else:
                    warning(
                        f"Source code directory or package '{src_subdir}' not found in package. Skipping."
                    )

            # Import Docker Image
            auto_confirm_docker = non_interactive_global or (not confirm_docker_image)
            if prompt_for_confirmation("Import Docker image", auto_confirm_docker):
                docker_dir = package_root_dir / self.PACKAGE_SUBDIRS["docker_image"]
                # Look for any .tar files in docker_image subdir
                docker_image_file = docker_dir / DEFAULT_IMAGE_EXPORT_FILENAME
                self.import_docker_image(docker_image_file)

            # Import Maps
            auto_confirm_maps = non_interactive_global or (not confirm_maps)
            if prompt_for_confirmation("Import maps", auto_confirm_maps):
                maps_subdir = package_root_dir / self.PACKAGE_SUBDIRS["maps"]
                maps_file_path = maps_subdir / DEFAULT_MAP_EXPORT_FILENAME
                print(f"Looking for maps at: {maps_file_path}")  # Debug print
                if maps_file_path.exists():
                    self.import_maps(
                        str(maps_file_path),
                        force_overwrite=force_individual_import_overwrite,
                    )
                else:
                    if maps_subdir.is_dir():
                        warning(
                            f"'{DEFAULT_MAP_EXPORT_FILENAME}' not found in '{maps_subdir}'. Attempting to import directory directly."
                        )
                        self.import_maps(
                            str(maps_subdir),
                            force_overwrite=force_individual_import_overwrite,
                        )
                    else:
                        warning(
                            f"Maps directory or package '{maps_subdir}' not found in package. Skipping."
                        )

            # Import Models
            auto_confirm_models = non_interactive_global or (not confirm_models)
            if prompt_for_confirmation("Import models", auto_confirm_models):
                models_subdir = package_root_dir / self.PACKAGE_SUBDIRS["models"]
                models_file_path = models_subdir / DEFAULT_MODEL_EXPORT_FILENAME
                # Debug print
                print(f"Looking for models at: {models_file_path}")
                if models_file_path.exists():
                    self.import_models(
                        str(models_file_path),
                        force_overwrite=force_individual_import_overwrite,
                    )
                else:
                    if models_subdir.is_dir():
                        warning(
                            f"'{DEFAULT_MODEL_EXPORT_FILENAME}' not found in '{models_subdir}'. Attempting to import directory directly."
                        )
                        self.import_models(
                            str(models_subdir),
                            force_overwrite=force_individual_import_overwrite,
                        )
                    else:
                        warning(
                            f"Models directory or package '{models_subdir}' not found in package. Skipping."
                        )

            # Import Cache
            auto_confirm_cache = non_interactive_global or (not confirm_cache)
            if prompt_for_confirmation("Import cache", auto_confirm_cache):
                cache_subdir = package_root_dir / self.PACKAGE_SUBDIRS["cache"]
                cache_file_path = cache_subdir / DEFAULT_CACHE_EXPORT_FILENAME
                # Debug print
                print(f"Looking for cache at: {cache_file_path}")
                if cache_file_path.exists():
                    self.import_cache(
                        str(cache_file_path),
                        force_overwrite=force_individual_import_overwrite,
                    )
                else:
                    warning(
                        f"Cache directory or package '{cache_subdir}' not found in package. Skipping."
                    )

        except Exception as e:
            error(f"Error during package import: {e}")
            raise OrchestratorError(f"Failed to import from package: {e}")
        finally:
            if temp_extract_dir.exists():
                info(f"Cleaning up temporary directory: {temp_extract_dir}")
                shutil.rmtree(temp_extract_dir)
        info("--- 🎉 Full Data Import Complete ---")

    # --- export_all (Modified to use consistent default input paths) ---
    def export_all(
        self,
        output_package_path: str,
        non_interactive_global: bool = False,
        confirm_source_code: bool = True,
        confirm_docker_image: bool = True,
        confirm_maps: bool = True,
        confirm_models: bool = True,
        confirm_cache: bool = True,
        docker_image_name: Optional[str] = None,
    ) -> None:
        """
        Exports selected data resources into a single combined package file.
        Global non_interactive_global flag or individual confirm_xxx flags control prompting.
        Default export sources are consistent with default import targets.
        """
        info("--- 📦 Starting Full Data Export to Package ---")
        output_package_path_obj = Path(output_package_path)
        temp_export_dir_root = (
            output_package_path_obj.parent
            / f"{output_package_path_obj.stem}_temp_export"
        )
        temp_export_dir_root.mkdir(parents=True, exist_ok=True)

        try:
            temp_resource_dirs = {}
            for res_key, res_subdir in self.PACKAGE_SUBDIRS.items():
                temp_resource_dirs[res_key] = temp_export_dir_root / res_subdir
                temp_resource_dirs[res_key].mkdir(exist_ok=True)

            # Export Source Code - Default input path is DEFAULT_SOURCE_DIR
            auto_confirm_src = non_interactive_global or (not confirm_source_code)
            if prompt_for_confirmation("Export source code", auto_confirm_src):
                info(
                    f"Exporting source code from '{DEFAULT_SOURCE_DIR}' to {temp_resource_dirs['source_code']}"
                )
                self.source_package_manager.export_source_package(
                    input_path=DEFAULT_SOURCE_DIR,
                    output_path=str(
                        temp_resource_dirs["source_code"]
                        / DEFAULT_SOURCE_EXPORT_FILENAME
                    ),
                )
                info("Source code exported.")

            # Export Docker Image - Default input image is DEFAULT_IMAGE_NAME
            auto_confirm_docker = non_interactive_global or (not confirm_docker_image)
            if prompt_for_confirmation("Export Docker image", auto_confirm_docker):
                image_to_export = (
                    docker_image_name
                    if docker_image_name
                    else DEFAULT_IMAGE_EXPORT_FILENAME
                )
                info(
                    f"Exporting Docker image '{image_to_export}' to {temp_resource_dirs['docker_image']}"
                )
                self.export_docker_image(
                    image_to_export,
                    str(
                        temp_resource_dirs["docker_image"]
                        / DEFAULT_IMAGE_EXPORT_FILENAME
                    ),
                )
                info("Docker image exported.")

            # Export Maps - Default input path is DEFAULT_MAP_IMPORT_DIR
            auto_confirm_maps = non_interactive_global or (not confirm_maps)
            if prompt_for_confirmation("Export maps", auto_confirm_maps):
                info(
                    f"Exporting maps from '{DEFAULT_MAP_IMPORT_DIR}' to {temp_resource_dirs['maps']}"
                )
                self.map_manager.export_map(
                    input_path=DEFAULT_MAP_IMPORT_DIR,
                    output_path=str(
                        temp_resource_dirs["maps"] / DEFAULT_MAP_EXPORT_FILENAME
                    ),
                )
                info("Maps exported.")

            # Export Models - Default input path is DEFAULT_MODEL_IMPORT_DIR
            auto_confirm_models = non_interactive_global or (not confirm_models)
            if prompt_for_confirmation("Export models", auto_confirm_models):
                info(
                    f"Exporting models from '{DEFAULT_MODEL_IMPORT_DIR}' to {temp_resource_dirs['models']}"
                )
                self.model_manager.export_model(
                    input_path=DEFAULT_MODEL_IMPORT_DIR,
                    output_path=str(
                        temp_resource_dirs["models"] / DEFAULT_MODEL_EXPORT_FILENAME
                    ),
                )
                info("Models exported.")

            # Export Cache - Default input path is BAZEL_CACHE_DIR
            auto_confirm_cache = non_interactive_global or (not confirm_cache)
            if prompt_for_confirmation("Export cache", auto_confirm_cache):
                info(
                    f"Exporting cache from '{BAZEL_CACHE_DIR}' to {temp_resource_dirs['cache']}"
                )
                self.export_cache(
                    input_path=BAZEL_CACHE_DIR,
                    output_path=str(
                        temp_resource_dirs["cache"] / DEFAULT_CACHE_EXPORT_FILENAME
                    ),
                )
                info("Cache exported.")

            info(f"Creating final package '{output_package_path}'...")
            with tarfile.open(output_package_path, "w") as tar:
                old_cwd = os.getcwd()
                os.chdir(temp_export_dir_root)
                for item in os.listdir("."):
                    tar.add(item)
                os.chdir(old_cwd)
            info(f"Final package created at: {output_package_path}")

        except Exception as e:
            error(f"Error during package export: {e}")
            raise OrchestratorError(f"Failed to export to package: {e}")
        finally:
            if temp_export_dir_root.exists():
                info(f"Cleaning up temporary directory: {temp_export_dir_root}")
                shutil.rmtree(temp_export_dir_root)
            info("--- 🎉 Full Data Export Complete ---")

    # --- Environment Setup (Individual) ---

    def setup_docker(self, uninstall: bool = False):
        info("--- Step: Setting up Docker Environment ---")
        action = (
            self.docker_manager.uninstall if uninstall else self.docker_manager.install
        )
        action()
        info("--- ✅ Docker Environment Setup Complete ---")

    def setup_nvidia_toolkit(self, uninstall: bool = False):
        info("--- Step: Setting up NVIDIA Container Toolkit ---")
        action = (
            self.nvidia_toolkit_manager.uninstall
            if uninstall
            else self.nvidia_toolkit_manager.install
        )
        action()
        info("--- ✅ NVIDIA Container Toolkit Setup Complete ---")

    def setup_host_config(self):
        info("--- Step: Configuring Host System ---")
        self.host_config_manager.setup_host_machine()
        info("--- ✅ Host System Configuration Complete ---")

    # --- Data Import (Individual) ---
    def import_source_code(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_overwrite: bool = True,
    ) -> None:
        info(
            f"Importing source code from '{input_path}' to '{output_path or DEFAULT_SOURCE_DIR}'..."
        )
        # If output_path is parent directory, DO NOT APPEND DEFAULT_SOURCE_DIR
        actual_output_path = (
            output_path if output_path is not None else DEFAULT_SOURCE_DIR
        )
        self.source_package_manager.import_source_package(
            input_path, actual_output_path, force_overwrite=force_overwrite
        )
        info("--- ✅ Source Code Import Complete ---")

    def import_docker_image(self, input_path: str) -> None:
        info(f"Importing docker image from '{input_path}'...")
        self.docker_image_manager.load_images(input_path)
        info("--- ✅ Docker Image Import Complete ---")

    def import_maps(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_overwrite: bool = False,
    ) -> None:
        info(
            f"Importing maps from '{input_path}' to '{output_path or DEFAULT_MAP_IMPORT_DIR}'..."
        )
        actual_output_path = (
            output_path if output_path is not None else DEFAULT_MAP_IMPORT_DIR
        )
        self.map_manager.import_map(
            input_path, actual_output_path, force_overwrite=force_overwrite
        )
        info("--- ✅ Maps Import Complete ---")

    def import_models(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_overwrite: bool = False,
    ) -> None:
        info(
            f"Importing models from '{input_path}' to '{output_path or DEFAULT_MODEL_IMPORT_DIR}'..."
        )
        actual_output_path = (
            output_path if output_path is not None else DEFAULT_MODEL_IMPORT_DIR
        )
        self.model_manager.import_model(
            input_path, actual_output_path, force_overwrite=force_overwrite
        )
        info("--- ✅ Models Import Complete ---")

    def import_cache(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_overwrite: bool = False,
    ) -> None:
        info(
            f"Importing cache from '{input_path}' to '{output_path or BAZEL_CACHE_DIR}'..."
        )
        actual_output_path = output_path if output_path is not None else BAZEL_CACHE_DIR
        self.cache_manager.import_cache(
            input_path, actual_output_path, force_overwrite=force_overwrite
        )
        info("--- ✅ Cache Import Complete ---")

    # --- Data Export (Individual) ---
    def export_docker_image(self, input_image_name: str, output_path: str) -> None:
        info(f"Exporting Docker image '{input_image_name}' to '{output_path}'...")
        self.docker_image_manager.save_images(input_image_name, output_path)
        info("--- ✅ Docker Image Export Complete ---")

    def export_maps(self, input_path: str, output_path: str) -> None:
        info(f"Exporting maps from '{input_path}' to '{output_path}'...")
        self.map_manager.export_map(input_path, output_path)
        info("--- ✅ Maps Export Complete ---")

    def export_models(self, input_path: str, output_path: str) -> None:
        info(f"Exporting models from '{input_path}' to '{output_path}'...")
        self.model_manager.export_model(input_path, output_path)
        info("--- ✅ Models Export Complete ---")

    def export_cache(self, input_path: Optional[str], output_path: str) -> None:
        info(
            f"Exporting cache from '{input_path or BAZEL_CACHE_DIR}' to '{output_path}'..."
        )
        # input_path can be None, use BAZEL_CACHE_DIR as default source
        actual_input_path = input_path if input_path is not None else BAZEL_CACHE_DIR
        self.cache_manager.export_cache(actual_input_path, output_path)
        info("--- ✅ Cache Export Complete ---")

    def export_source_package(
        self, input_path: Optional[str], output_path: str
    ) -> None:
        info(
            f"Exporting source code from '{input_path or DEFAULT_SOURCE_DIR}' to '{output_path}'..."
        )
        # input_path can be None, use DEFAULT_SOURCE_DIR as default source
        actual_input_path = input_path if input_path is not None else DEFAULT_SOURCE_DIR
        self.source_package_manager.export_source_package(
            actual_input_path, output_path
        )
        info("--- ✅ Source Code Export Complete ---")


# --- Script Entry Point ---


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous driving platform host setup and data management tool.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.set_defaults(func=lambda args: parser.print_help())
    parser.add_argument(
        "--mirror",
        type=str,
        default=None,
        choices=["CN", "US"],
        help="Specify mirror region for downloads. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default="apollo",
        help='Specify workspace directory. Defaults to "apollo".',
    )
    subparsers = parser.add_subparsers(dest="command", help="Main command to execute")

    # --- Setup Parser ---
    setup_parser = subparsers.add_parser(
        "setup", help="Install, uninstall or configure host components."
    )
    setup_subparsers = setup_parser.add_subparsers(
        dest="component", required=True, help="Component or flow to run"
    )

    p_setup_all = setup_subparsers.add_parser(
        "all", help="Run the full interactive setup process."
    )
    p_setup_all.add_argument(
        "--uninstall", action="store_true", help="Perform uninstall instead of install."
    )
    p_setup_all.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help='Assume "yes" to all prompts (non-interactive).',
    )

    for comp in ["docker", "nvidia", "host"]:
        p = setup_subparsers.add_parser(comp, help=f"Manage {comp} setup individually.")
        if comp != "host":
            p.add_argument(
                "--uninstall",
                action="store_true",
                help="Perform uninstall instead of install.",
            )

    # --- Import Parser ---
    import_parser = subparsers.add_parser("import", help="Import data into the system.")
    import_subparsers = import_parser.add_subparsers(
        dest="resource", required=True, help="Resource to import"
    )

    p_import_all = import_subparsers.add_parser(
        "all",
        help="Run the full interactive import process for specified resources from a single package.",
    )
    p_import_all.add_argument(
        "--package",
        type=str,
        required=True,
        help="Path to the combined package .tar archive to import.",
    )
    p_import_all.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help='Assume "yes" to all prompts (non-interactive).',
    )

    # Individual import subcommands (minor adjustment for clarity in import_xxx)
    p_src_import = import_subparsers.add_parser(
        "source_code", help="Import source code package"
    )
    p_src_import.add_argument(
        "--input",
        type=str,
        default=DEFAULT_SOURCE_EXPORT_FILENAME,
        help="Path/URL to the source code package",
    )
    p_src_import.add_argument(
        "--output",
        type=str,
        default=DEFAULT_SOURCE_DIR,
        help=f"Target directory for extraction (defaults to {DEFAULT_SOURCE_DIR})",
    )
    p_src_import.add_argument(
        "--noforce",
        action="store_false",
        dest="force_overwrite",
        help="Do not force overwrite existing content (i.e., ask for confirmation).",
    )
    p_src_import.set_defaults(force_overwrite=True)

    p_docker_import = import_subparsers.add_parser(
        "docker_image", help="Import Docker image archive"
    )
    p_docker_import.add_argument(
        "--input",
        type=str,
        default=DEFAULT_IMAGE_EXPORT_FILENAME,
        help="Path to the Docker image .tar archive",
    )

    p_maps_import = import_subparsers.add_parser("maps", help="Import maps archive")
    p_maps_import.add_argument(
        "--input",
        type=str,
        default=DEFAULT_MAP_EXPORT_FILENAME,
        help="Path to the maps .tar archive",
    )
    p_maps_import.add_argument(
        "--output",
        type=str,
        default=DEFAULT_MAP_IMPORT_DIR,
        help=f"Target directory for extraction (defaults to {DEFAULT_MAP_IMPORT_DIR})",
    )
    p_maps_import.add_argument(
        "--noforce",
        action="store_false",
        dest="force_overwrite",
        help="Do not force overwrite existing content (i.e., ask for confirmation).",
    )
    p_maps_import.set_defaults(force_overwrite=True)

    p_models_import = import_subparsers.add_parser(
        "models", help="Import models archive"
    )
    p_models_import.add_argument(
        "--input",
        type=str,
        default=DEFAULT_MODEL_EXPORT_FILENAME,
        help="Path to the models .tar archive",
    )
    p_models_import.add_argument(
        "--output",
        type=str,
        default=DEFAULT_MODEL_IMPORT_DIR,
        help=f"Target directory for extraction (defaults to {DEFAULT_MODEL_IMPORT_DIR})",
    )
    p_models_import.add_argument(
        "--noforce",
        action="store_false",
        dest="force_overwrite",
        help="Do not force overwrite existing content (i.e., ask for confirmation).",
    )
    p_models_import.set_defaults(force_overwrite=True)

    p_cache_import = import_subparsers.add_parser(
        "cache", help="Import Bazel cache archive"
    )
    p_cache_import.add_argument(
        "--input",
        type=str,
        default=DEFAULT_CACHE_EXPORT_FILENAME,
        help="Path to the cache .tar archive",
    )
    p_cache_import.add_argument(
        "--output",
        type=str,
        default=BAZEL_CACHE_DIR,
        help=f"Target directory for extraction (defaults to {BAZEL_CACHE_DIR})",
    )
    p_cache_import.add_argument(
        "--noforce",
        action="store_false",
        dest="force_overwrite",
        help="Do not force overwrite existing content (i.e., ask for confirmation).",
    )
    p_cache_import.set_defaults(force_overwrite=True)

    # --- Export Parser ---
    export_parser = subparsers.add_parser("export", help="Export data from the system.")
    export_subparsers = export_parser.add_subparsers(
        dest="resource", required=True, help="Resource to export"
    )

    p_export_all = export_subparsers.add_parser(
        "all",
        help="Run the full interactive export process for specified resources into a single package.",
    )
    p_export_all.add_argument(
        "--package",
        type=str,
        required=True,
        help="Path to save the combined package .tar archive.",
    )
    p_export_all.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help='Assume "yes" to all prompts (non-interactive).',
    )
    p_export_all.add_argument(
        "--docker_image",
        type=str,
        default=DEFAULT_IMAGE_NAME,
        help=f'Specify the name of the Docker image to export (e.g., ubuntu:latest). Defaults to "{DEFAULT_IMAGE_NAME}".',
    )

    # Individual export subcommands (minor adjustment for clarity in export_xxx)
    p_src_export = export_subparsers.add_parser(
        "source_code", help="Export source code package"
    )
    p_src_export.add_argument(
        "--input",
        type=str,
        default=DEFAULT_SOURCE_DIR,
        help=f"Path to the source code directory to export (defaults to {DEFAULT_SOURCE_DIR})",
    )
    p_src_export.add_argument(
        "--output",
        type=str,
        default=DEFAULT_SOURCE_EXPORT_FILENAME,
        help="Path to save the output .tar archive",
    )

    p_docker_export = export_subparsers.add_parser(
        "docker_image", help="Export a Docker image"
    )
    p_docker_export.add_argument(
        "--input",
        type=str,
        default=DEFAULT_IMAGE_NAME,
        help="Name of the Docker image to export (e.g., ubuntu:latest)",
    )
    p_docker_export.add_argument(
        "--output",
        type=str,
        default=DEFAULT_IMAGE_EXPORT_FILENAME,
        help="Path to save the output .tar archive (e.g., ./image.tar)",
    )
    p_docker_export.add_argument(
        "--info", action="store_true", help="List available local Docker images."
    )

    p_maps_export = export_subparsers.add_parser("maps", help="Export a map")
    p_maps_export.add_argument(
        "--input",
        type=str,
        default=DEFAULT_MAP_IMPORT_DIR,
        help=f"Path to the map directory to export (defaults to {DEFAULT_MAP_IMPORT_DIR})",
    )
    p_maps_export.add_argument(
        "--output",
        type=str,
        default=DEFAULT_MAP_EXPORT_FILENAME,
        help="Path to save the output .tar archive",
    )

    p_models_export = export_subparsers.add_parser("models", help="Export a model")
    p_models_export.add_argument(
        "--input",
        type=str,
        default=DEFAULT_MODEL_IMPORT_DIR,
        help=f"Path to the model directory to export (defaults to {DEFAULT_MODEL_IMPORT_DIR})",
    )
    p_models_export.add_argument(
        "--output",
        type=str,
        default=DEFAULT_MODEL_EXPORT_FILENAME,
        help="Path to save the output .tar archive",
    )

    p_cache_export = export_subparsers.add_parser(
        "cache", help="Export the Bazel cache"
    )
    p_cache_export.add_argument(
        "--input",
        type=str,
        default=BAZEL_CACHE_DIR,
        help=f"Path to the cache directory to export (defaults to {BAZEL_CACHE_DIR})",
    )
    p_cache_export.add_argument(
        "--output",
        type=str,
        default=DEFAULT_CACHE_EXPORT_FILENAME,
        help="Path to save the output .tar archive",
    )

    args = parser.parse_args()

    # Determine mirror region
    if not can_access_github():
        mirror_region = "CN"
    else:
        mirror_region = "US"
    if args.mirror:
        mirror_region = args.mirror
    info(f"Using mirror region: {mirror_region}")

    orchestrator = HostSetupOrchestrator(mirror_region)

    try:
        if not hasattr(args, "command") or args.command is None:
            parser.print_help()
            sys.exit(0)

        if args.command == "setup":
            if args.component == "all":
                orchestrator.setup_all(
                    non_interactive=args.yes, uninstall=args.uninstall
                )
            elif args.component == "docker":
                orchestrator.setup_docker(args.uninstall)
            elif args.component == "nvidia":
                orchestrator.setup_nvidia_toolkit(args.uninstall)
            elif args.component == "host":
                orchestrator.setup_host_config()

        elif args.command == "import":
            if args.resource == "all":
                orchestrator.import_all(
                    package_path=args.package,
                    non_interactive_global=args.yes,
                    confirm_source_code=False,
                    confirm_docker_image=False,
                    confirm_maps=True,
                    confirm_models=True,
                    confirm_cache=False,
                )
            elif args.resource == "source_code":
                orchestrator.import_source_code(
                    args.input, args.output, force_overwrite=args.force_overwrite
                )
            elif args.resource == "docker_image":
                orchestrator.import_docker_image(args.input)
            elif args.resource == "maps":
                orchestrator.import_maps(
                    args.input, args.output, force_overwrite=args.force_overwrite
                )
            elif args.resource == "models":
                orchestrator.import_models(
                    args.input, args.output, force_overwrite=args.force_overwrite
                )
            elif args.resource == "cache":
                orchestrator.import_cache(
                    args.input, args.output, force_overwrite=args.force_overwrite
                )

        elif args.command == "export":
            if args.resource == "all":
                orchestrator.export_all(
                    output_package_path=args.package,
                    non_interactive_global=args.yes,
                    docker_image_name=args.docker_image,
                    confirm_source_code=False,
                    confirm_docker_image=False,
                    confirm_maps=True,
                    confirm_models=True,
                    confirm_cache=False,
                )
            elif args.resource == "source_code":
                orchestrator.export_source_package(args.input, args.output)
            elif args.resource == "docker_image":
                if args.info:
                    local_image_tags = (
                        orchestrator.docker_image_manager.get_local_image_tags()
                    )
                    if local_image_tags:
                        info("Available local images (REPOSITORY:TAG) on your system:")
                        for tag in local_image_tags:
                            info(f"  - {tag}")
                        info("\n")
                    else:
                        warning(
                            "Could not retrieve local Docker image list. Please ensure Docker daemon is running."
                        )
                else:  # Default is to require --input for individual docker_image export
                    orchestrator.export_docker_image(args.input, args.output)
            elif args.resource == "maps":
                orchestrator.export_maps(args.input, args.output)
            elif args.resource == "models":
                orchestrator.export_models(args.input, args.output)
            elif args.resource == "cache":
                orchestrator.export_cache(args.input, args.output)

    except (OrchestratorError, ManagerError) as e:
        error(f"Operation failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        info("Operation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
