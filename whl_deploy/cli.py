#!/usr/bin/env python3

import argparse
import sys

from whl_deploy.orchestrator import HostSetupOrchestrator, OrchestratorError
from whl_deploy.utils.common import info, error, critical
from whl_deploy.utils.prompt import show_welcome
from whl_deploy.host.env_manager import HostEnvManager


def configure_parser() -> argparse.ArgumentParser:
    """Configure the argument parser for the application."""
    parser = argparse.ArgumentParser(
        description="Autonomous driving platform host setup and data management tool.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.set_defaults(func=lambda args: parser.print_help())
    parser.add_argument(
        "--workspace",
        type=str,
        default=".",
        help='Specify workspace directory. Defaults: "apollo".',
    )

    subparsers = parser.add_subparsers(dest="command", help="Main command to execute")

    # Setup commands
    setup_parser = subparsers.add_parser(
        "setup", help="Install, uninstall or configure host env."
    )
    setup_subparsers = setup_parser.add_subparsers(
        dest="component", required=True, help="Component to setup"
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

    for comp in ["docker", "nvidia_toolkit"]:
        p = setup_subparsers.add_parser(comp, help=f"Manage {comp} setup individually.")
        p.add_argument(
            "--uninstall",
            action="store_true",
            help="Perform uninstall instead of install.",
        )

    # Import commands
    import_parser = subparsers.add_parser("import", help="Import data into the system.")
    import_subparsers = import_parser.add_subparsers(
        dest="resource", required=True, help="Resource to import"
    )
    p_import_all = import_subparsers.add_parser(
        "all", help="Run the full interactive import process."
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

    for resource in ["source_code", "docker_image", "maps", "models", "cache"]:
        p = import_subparsers.add_parser(
            resource, help=f"Import {resource.replace('_', ' ')}"
        )
        p.add_argument(
            "-i",
            "--input",
            type=str,
            required=True,
            help="Path to the resource package",
        )
        p.add_argument("--output", type=str, help="Target directory for extraction")
        p.add_argument(
            "--noforce",
            action="store_false",
            dest="force_overwrite",
            help="Do not force overwrite existing content.",
        )
        p.set_defaults(force_overwrite=True)

    # Export commands
    export_parser = subparsers.add_parser("export", help="Export data from the system.")
    export_subparsers = export_parser.add_subparsers(
        dest="resource", required=True, help="Resource to export"
    )
    p_export_all = export_subparsers.add_parser(
        "all", help="Run the full interactive export process."
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

    for resource in ["source_code", "docker_image", "maps", "models", "cache"]:
        p = export_subparsers.add_parser(
            resource, help=f"Export {resource.replace('_', ' ')}"
        )
        p.add_argument(
            "--input",
            type=str,
            required=True,
            help="Path to the resource directory to export",
        )
        p.add_argument(
            "--output",
            type=str,
            required=True,
            help="Path to save the output .tar archive",
        )

    return parser


def main():
    show_welcome()

    parser = configure_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # Check the host environment
    manager = HostEnvManager()
    try:
        manager.check_host_environment()
    except EnvironmentError as e:
        error(str(e))
        sys.exit(1)

    # Setup Host
    orchestrator = HostSetupOrchestrator()

    try:
        if args.command == "setup":
            if args.component == "all":
                orchestrator.setup_all(uninstall=args.uninstall)
            else:
                method_name = f"setup_{args.component}"
                getattr(orchestrator.host_setup, method_name)(args.uninstall)
        elif args.command == "import":
            if args.resource == "all":
                orchestrator.import_all(
                    package_path=args.package, non_interactive=args.yes
                )
            else:
                orchestrator.resource_importer._import_resource(
                    args.resource, args.input, False
                )
        elif args.command == "export":
            if args.resource == "all":
                orchestrator.export_all(args.package)
            else:
                # Call specific export method
                method_name = f"export_{args.resource}"
                getattr(orchestrator.resource_exporter, method_name)(
                    args.input, args.output
                )

    except OrchestratorError as e:
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
