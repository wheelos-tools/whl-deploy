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


import argparse
import sys
import traceback
from pathlib import Path

from whl_deploy.core.base import DeployContext
from whl_deploy.core.orchestrator import Orchestrator
from whl_deploy.utils.prompt import show_welcome
from whl_deploy.utils.common import configure_logging, error, info
from whl_deploy.utils.system import SystemInfoCollector


def configure_parser() -> argparse.ArgumentParser:
    """Configure the command-line argument parser."""

    # 1. Define common arguments (inherited by subcommands)
    common_parser = argparse.ArgumentParser(add_help=False)

    common_parser.add_argument(
        "--manifest",
        "-m",
        type=str,
        default=None,
        help="Path to the manifest definition (default: manifest.yaml in current/extracted dir).",
    )

    common_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging for debugging.",
    )

    # 2. Main Parser
    parser = argparse.ArgumentParser(
        description="WheelOS Deployment Tool (Pack & Install)",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Operation mode", metavar="COMMAND"
    )

    # ==========================================
    # 3. Pack Command
    # ==========================================
    pack_parser = subparsers.add_parser(
        "pack",
        aliases=["p"],
        parents=[common_parser],
        help="Create a consolidated release package. (Alias: p)",
    )

    # ==========================================
    # 4. Install Command
    # ==========================================
    install_parser = subparsers.add_parser(
        "install",
        aliases=["i", "run", "r"],
        parents=[common_parser],
        help="Deploy artifacts to the host system. (Alias: i)",
    )

    install_parser.add_argument(
        "--bundle",
        "-b",
        type=str,
        default=None,
        help="Path to the .tar release bundle to unpack and install.",
    )

    return parser


def normalize_command(command: str) -> str:
    """Maps aliases (p, i) back to canonical command names (pack, install)."""
    mapping = {
        "p": "pack",
        "i": "install",
        "r": "install",
        "run": "install",
    }
    return mapping.get(command, command)


def main():
    # 1. Parse Arguments
    parser = configure_parser()
    args = parser.parse_args()

    # 2. Configure Logging
    configure_logging(verbose=args.verbose)

    # 3. Show Welcome Banner
    show_welcome()

    try:
        # 4. Normalize Command
        mode = normalize_command(args.command)

        # 5. Initialize Context
        bundle_path = getattr(args, "bundle", None)

        ctx = DeployContext(
            workspace=Path.cwd(),
            manifest_path=args.manifest,
            bundle_path=bundle_path,
            mode=mode,
        )

        # Collect system info immediately (always useful)
        SystemInfoCollector.collect(ctx)

        # 6. Start Orchestrator
        orchestrator = Orchestrator(ctx)
        orchestrator.run()

        # 7. Save Manifest
        if ctx.manifest:
            ctx.save_manifest()

        info(f"✨ Operation '{mode}' completed successfully!")
        sys.exit(0)

    except FileNotFoundError as e:
        error(f"Configuration Error: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n")
        error("⚠️  Operation cancelled by user.")
        sys.exit(130)

    except Exception as e:
        print("\n")
        error(f"Fatal Error: {e}")
        if args.verbose:
            print("\n--- Traceback ---")
            traceback.print_exc()
        else:
            print("   (Run with --verbose to see full traceback)")
        sys.exit(1)


if __name__ == "__main__":
    main()
