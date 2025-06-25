#!/usr/bin/env python3

import sys
import argparse
import yaml
from typing import Dict, Optional, Any, Callable
from pathlib import Path
import importlib.resources as pkg_resources


from whl_deploy.common import info, error, warning, critical, logger, ManagerError
from whl_deploy.prompt import print_help
from whl_deploy.ip_country_checker import get_ip_country_code

from whl_deploy.prepare.install_docker import DockerManager
from whl_deploy.prepare.install_nvidia_container_toolkit import NvidiaToolkitManager
from whl_deploy.prepare.config_system import HostConfigManager
from whl_deploy.resource.cache import CacheManager
from whl_deploy.resource.docker_image import DockerImageManager
from whl_deploy.resource.maps import MapManager
from whl_deploy.resource.models import ModelManager
from whl_deploy.resource.source_code import SourcePackageManager

# --- Global Constants ---
BUILTIN_DATA_PACKAGE = 'whl_deploy.data'
DEFAULT_CONFIG_FILENAME = "config.yaml"


# --- Custom Exceptions ---
class OrchestratorError(Exception):
    """Custom exception for errors during orchestration processes."""
    pass


class HostSetupOrchestrator:
    """
    Orchestrates the setup of the host environment and the import/export of data.
    """

    def __init__(self, mirror_region: Optional[str] = None):
        info("Initializing Host Setup Orchestrator...")
        self.mirror_region = mirror_region
        # Initialize all managers
        self.docker_manager = DockerManager(mirror_region=self.mirror_region)
        self.nvidia_toolkit_manager = NvidiaToolkitManager(
            mirror_region=self.mirror_region)
        self.host_config_manager = HostConfigManager()
        self.cache_manager = CacheManager(logger_instance=logger)
        self.docker_image_manager = DockerImageManager(logger_instance=logger)
        self.map_manager = MapManager(logger_instance=logger)
        self.model_manager = ModelManager(logger_instance=logger)
        self.source_package_manager = SourcePackageManager(
            logger_instance=logger)

    # --- Environment Setup ---
    def setup_docker(self, uninstall: bool = False):
        info("--- Step 1: Setting up Docker Environment ---")
        action = self.docker_manager.uninstall if uninstall else self.docker_manager.install
        action()
        info("--- ✅ Docker Environment Setup Complete ---")

    def setup_nvidia_toolkit(self, uninstall: bool = False):
        info("--- Step 2: Setting up NVIDIA Container Toolkit ---")
        action = self.nvidia_toolkit_manager.uninstall if uninstall else self.nvidia_toolkit_manager.install
        action()
        info("--- ✅ NVIDIA Container Toolkit Setup Complete ---")

    def setup_host_config(self):
        info("--- Step 3: Configuring Host System ---")
        self.host_config_manager.setup_host_machine()
        info("--- ✅ Host System Configuration Complete ---")

    def default_setup_and_import(self, defaults_file_path: Optional[str] = None, interactive: bool = True):
        """Runs the full setup sequence and then the data import."""
        info("--- 🚀 Starting Full Setup and Data Import ---")
        try:
            self.setup_docker()
            self.setup_nvidia_toolkit()
            self.setup_host_config()
            self.import_data(config_file_path=defaults_file_path,
                             interactive=interactive)
            info("--- 🎉 Full Setup and Data Import Complete ---")
        except Exception as e:
            critical(f"Full setup and import process failed: {e}")
            print_help("An error occurred during the automated full run.")
            raise

    # --- Data Import/Export ---
    def import_data(self, config_file_path: Optional[str], interactive: bool) -> None:
        """Imports data based on a config file, optionally with interactive override."""
        info("--- 📦 Starting Data Import ---")

        # Add defaults then user config
        config = self._load_and_merge_configs(config_file_path)
        import_config = config.get('import_data', {})
        if not import_config:
            warning(
                "No 'import_data' section found in configuration. Nothing to import.")
            return

        info("\n--- Executing data import ---")

        def _import_resource(key: str, prompt: str, manager_func: Callable[[str], Any]):
            path = import_config.get(key)
            if interactive:
                path = self._prompt_for_input(prompt, path)

            if path:
                info(f"Importing {key.replace('_', ' ')} from '{path}'...")
                manager_func(path)
            else:
                info(
                    f"Skipping {key.replace('_', ' ')} import (no path provided).")

        _import_resource('source_code', "Enter source code location (URL or path)",
                         self.source_package_manager.import_source_package)
        _import_resource('docker_images', "Enter Docker images archive location",
                         self.docker_image_manager.load_images)
        _import_resource('maps', "Enter maps archive location",
                         self.map_manager.import_map)
        _import_resource('models', "Enter models archive location",
                         self.model_manager.import_model)
        _import_resource('cache', "Enter cache archive location",
                         self.cache_manager.import_cache)

        info("--- ✅ Data Import Complete ---")

    def export_data(self, config_file_path: str) -> None:
        """Exports data based on a configuration file."""
        info(
            f"--- 📤 Starting data export using config: {config_file_path} ---")

        config = self._load_and_merge_configs(config_file_path)

        export_config = config.get('export_destinations')
        if not export_config or not isinstance(export_config, dict):
            warning(
                "No 'export_destinations' section found in the config file or it's not a dictionary. Nothing to export.")
            return

        def _export_resource(key: str, manager_func: Callable[[str], Any]):
            destination = export_config.get(key)
            if destination:
                info(
                    f"Exporting {key.replace('_', ' ')} to '{destination}'...")
                try:
                    manager_func(str(destination))
                except AttributeError:
                    error(
                        f"Export function not implemented in the manager for '{key}'.")
                except Exception as e:
                    error(f"Failed to export {key.replace('_', ' ')}: {e}")
            else:
                info(
                    f"Skipping {key.replace('_', ' ')} export (no destination specified).")

        _export_resource(
            'source_code', self.source_package_manager.export_source_package)
        _export_resource(
            'docker_images', self.docker_image_manager.save_images)
        _export_resource('maps', self.map_manager.export_map)
        _export_resource('models', self.model_manager.export_model)
        _export_resource('cache', self.cache_manager.export_cache)

        info("--- ✅ Data Export Complete. ---")

    # --- Helper Methods ---
    def _load_config_from_file(self, config_path: Path) -> Dict:
        """Loads a single YAML configuration file."""
        info(f"Attempting to load config from: {config_path}")
        try:
            with config_path.open('r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                info(f"Successfully loaded config from: {config_path}")
                return config if isinstance(config, dict) else {}
        except FileNotFoundError:
            warning(f"Config file not found at '{config_path}'.")
        except yaml.YAMLError as e:
            warning(f"Could not parse YAML file '{config_path}': {e}")
        return {}

    def _load_and_merge_configs(self, user_config_path: Optional[str]) -> Dict:
        """Loads built-in defaults and merges user-provided config on top."""
        # 1. Load built-in defaults from package
        defaults = {}
        try:
            with pkg_resources.open_text(BUILTIN_DATA_PACKAGE, DEFAULT_CONFIG_FILENAME) as f:
                defaults = yaml.safe_load(f) or {}
                info("Successfully loaded built-in default config.")
        except (FileNotFoundError, ModuleNotFoundError):
            warning(
                "Built-in config not found. This might indicate a packaging issue.")
        except Exception as e:
            warning(f"Could not load or parse built-in config: {e}")

        # 2. If a user config file is provided, load it
        user_config = {}
        if user_config_path:
            user_config = self._load_config_from_file(Path(user_config_path))

        # 3. Merge user config into defaults (user values override defaults)
        if defaults and user_config:
            # A simple deep merge for one level
            for key, value in user_config.items():
                if key in defaults and isinstance(defaults[key], dict) and isinstance(value, dict):
                    defaults[key].update(value)
                else:
                    defaults[key] = value
            return defaults

        return user_config or defaults

    def _prompt_for_input(self, prompt_text: str, default_value: Optional[str] = "") -> str:
        """Prompts the user for input, showing a default value."""
        default_display = default_value if default_value else "None"
        user_input = input(
            f"{prompt_text} [Default: {default_display}]: ").strip()
        return user_input or (default_value or "")


# --- Script Entry Point ---
def main():
    parser = argparse.ArgumentParser(
        description="Apollo autonomous driving platform host setup and data management tool.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--mirror', type=str, default='CN', choices=['CN', 'US'],
                        help='Specify mirror region for downloads (default: CN).')

    parser.add_argument('--config', type=str, default=None,
                        help='Path to a custom YAML config file. Used for import/export and can override built-in defaults.')

    subparsers = parser.add_subparsers(
        dest='command', help='Main command to execute')

    # --- Setup Parser ---
    setup_parser = subparsers.add_parser(
        'setup', help='Install and configure host environment components.')
    setup_subparsers = setup_parser.add_subparsers(
        dest='component', required=True, help='Component to set up')
    for comp in ['docker', 'nvidia', 'host']:
        p = setup_subparsers.add_parser(comp, help=f'Manage {comp} setup.')
        if comp != 'host':
            p.add_argument('--uninstall', action='store_true',
                           help='Perform uninstall instead of install.')

    # --- Import Parser ---
    import_parser = subparsers.add_parser(
        'import', help='Import data into the system.')
    import_parser.add_argument('--interactive', action='store_true',
                               help='Run in interactive mode, prompting for each resource path. Overrides config file values.')

    # --- Export Parser ---
    export_parser = subparsers.add_parser(
        'export', help='Export data from the system.')
    export_parser.add_argument('config', type=str, metavar='PATH',
                               help='Path to a YAML config file specifying what to export and where.')

    args = parser.parse_args()

    # first use args.mirror
    mirror_region = args.mirror
    if not mirror_region:
        mirror_region = get_ip_country_code()
    orchestrator = HostSetupOrchestrator(mirror_region)

    try:
        if args.command is None:
            orchestrator.default_setup_and_import(
                defaults_file_path=args.config, interactive=True)
            return

        if args.command == 'setup':
            if args.component == 'docker':
                orchestrator.setup_docker(args.uninstall)
            elif args.component == 'nvidia':
                orchestrator.setup_nvidia_toolkit(args.uninstall)
            elif args.component == 'host':
                orchestrator.setup_host_config()
        elif args.command == 'import':
            # If --config is not specified and --interactive is not provided, default to running non-interactively
            # If only --config is provided, non-interactive import
            # If --interactive is provided, interactive import, prompt for overwrite even with --config
            orchestrator.import_data(
                config_file_path=args.config, interactive=args.interactive)
        elif args.command == 'export':
            orchestrator.export_data(args.config)

    except (OrchestratorError, ManagerError) as e:
        print_help(f"Operation failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        warning("\nOperation interrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        print_help("The system encountered an unexpected error.")
        sys.exit(1)


if __name__ == "__main__":
    main()
