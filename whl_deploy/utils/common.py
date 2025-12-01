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



import logging
import os
import subprocess
import sys
import shutil
from typing import List, Optional, Dict, Union, TypeVar, Any
from pathlib import Path

# --- Setup Logging ---


# Define ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    GRAY = "\033[90m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors based on log level."""

    FORMAT = "%(message)s"

    FORMATS = {
        logging.DEBUG: Colors.GRAY + " [DEBUG] " + Colors.RESET + FORMAT,
        logging.INFO: Colors.BLUE + " [INFO]  " + Colors.RESET + FORMAT,
        logging.WARNING: Colors.YELLOW + " [WARN]  " + Colors.RESET + FORMAT,
        logging.ERROR: Colors.RED + " [ERROR] " + Colors.RESET + FORMAT,
        logging.CRITICAL: Colors.RED
        + Colors.BOLD
        + " [FATAL] "
        + Colors.RESET
        + FORMAT,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup_logger(name: str = "whl_deploy") -> logging.Logger:
    """Configures and returns a singleton logger instance."""
    logger = logging.getLogger(name)

    # Prevent adding multiple handlers if function is called repeatedly
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(ColoredFormatter())
        logger.addHandler(handler)

        # Default level is INFO
        logger.setLevel(logging.INFO)

        # Prevent propagation to root logger to avoid double printing
        logger.propagate = False

    return logger


def configure_logging(verbose: bool = False):
    """Updates the log level based on verbosity flag."""
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)
    if verbose:
        logger.debug("Verbose logging enabled.")


# --- Initialization ---

# Initialize the default logger instance
logger = setup_logger()

# Export convenient aliases for use in other modules
debug = logger.debug
info = logger.info
warning = logger.warning
error = logger.error
critical = logger.critical


# --- Custom Exceptions ---


class CommandExecutionError(Exception):
    """Custom exception for errors during command execution."""

    def __init__(self, message, returncode=None, stdout=None, stderr=None):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ManagerError(Exception):
    """Custom exception for errors during orchestration processes."""

    pass


# --- Utility Functions ---


def execute_command(
    command: List[str],
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    use_sudo: bool = False,
    input_data: Optional[Union[str, bytes]] = None,
    cwd: Optional[str] = None,
    log_output: bool = False,
) -> subprocess.CompletedProcess:
    """
    Executes a shell command using subprocess.run.

    Args:
        command: The command list.
        check: Raise exception on non-zero exit code.
        capture_output: Capture stdout/stderr.
        text: Decode stdout/stderr as text.
        use_sudo: Prepend 'sudo' to command.
        input_data: String or bytes to pass to stdin.
        cwd: Working directory.
        log_output: If True, log stdout/stderr to info level.
    """
    cmd_list = list(command)
    if use_sudo:
        cmd_list.insert(0, "sudo")

    # Convert input string to bytes if necessary
    if input_data is not None and isinstance(input_data, str):
        input_data = input_data.encode()

    if input_data is not None:
        text = False

    debug(f"Executing: {' '.join(cmd_list)}")

    try:
        result = subprocess.run(
            cmd_list,
            capture_output=capture_output,
            text=text,
            input=input_data,
            cwd=cwd,
            check=False,  # Checked manually below
        )

        if log_output and capture_output:
            if result.stdout:
                for line in result.stdout.splitlines():
                    info(f"  [STDOUT] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    warning(f"  [STDERR] {line}")

        if check and result.returncode != 0:
            err_msg = (
                f"Command failed (Exit: {result.returncode}): {' '.join(cmd_list)}"
            )
            # Log the output if it wasn't logged already so we know why it failed
            if not log_output and capture_output:
                if result.stderr:
                    error(f"STDERR: {result.stderr.strip()}")
                if result.stdout:
                    debug(f"STDOUT: {result.stdout.strip()}")

            raise CommandExecutionError(
                err_msg,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        return result

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Command not found: '{cmd_list[0]}'. Ensure it is installed/in PATH."
        )
    except Exception as e:
        error(f"Unexpected execution error: {e}")
        raise


def execute_docker_command(
    command_args: List[str],
    capture_output: bool = True,
    text: bool = True,
    check: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Wrapper for executing Docker commands with sudo."""
    return execute_command(
        ["docker"] + command_args,
        capture_output=capture_output,
        text=text,
        check=check,
        use_sudo=True,
        **kwargs,
    )


def get_os_info() -> Dict[str, str]:
    """
    Gets OS distribution info (ID, VERSION_ID/CODENAME).
    Normalized keys: 'ID', 'VERSION_ID', 'CODENAME'.
    """
    os_info = {}

    # Method 1: lsb_release
    if shutil.which("lsb_release"):
        try:
            res_id = (
                execute_command(["lsb_release", "-is"], capture_output=True)
                .stdout.strip()
                .lower()
            )
            res_code = (
                execute_command(["lsb_release", "-cs"], capture_output=True)
                .stdout.strip()
                .lower()
            )
            os_info["ID"] = res_id
            os_info["CODENAME"] = res_code
            # Attempt to get version ID as well
            res_ver = execute_command(
                ["lsb_release", "-rs"], capture_output=True
            ).stdout.strip()
            os_info["VERSION_ID"] = res_ver
            return os_info
        except Exception:
            pass  # Fallback

    # Method 2: /etc/os-release
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    # remove quotes
                    val = val.strip('"').strip("'")
                    if key == "ID":
                        os_info["ID"] = val.lower()
                    elif key == "VERSION_CODENAME":
                        os_info["CODENAME"] = val.lower()
                    elif key == "VERSION_ID":
                        os_info["VERSION_ID"] = val
                    elif key == "UBUNTU_CODENAME" and "CODENAME" not in os_info:
                        os_info["CODENAME"] = val.lower()

        # Default codename mapping if missing (simple fallback for common ubuntu versions)
        if "CODENAME" not in os_info and os_info.get("ID") == "ubuntu":
            v = os_info.get("VERSION_ID", "")
            if v.startswith("20.04"):
                os_info["CODENAME"] = "focal"
            elif v.startswith("22.04"):
                os_info["CODENAME"] = "jammy"
            elif v.startswith("24.04"):
                os_info["CODENAME"] = "noble"

        return os_info
    except FileNotFoundError:
        raise RuntimeError("Cannot determine OS: /etc/os-release not found.")


def ensure_dir(t_dir: Union[str, Path], mode: str = "0775") -> None:
    """
    Ensures a directory exists with specific permissions and ownership.
    Uses sudo for creation/chown if necessary.
    """
    path = Path(t_dir).resolve()

    info(f"Ensuring directory: {path}")

    # 1. Create directory
    if not path.exists():
        try:
            # Try python native first (faster, safer if no sudo needed)
            path.mkdir(parents=True, mode=int(mode, 8))
        except PermissionError:
            # Fallback to sudo
            info(f"Permission denied creating {path}, trying sudo...")
            execute_command(["mkdir", "-p", str(path)], use_sudo=True)
    elif not path.is_dir():
        raise FileExistsError(f"Path '{path}' exists but is not a directory.")

    # 2. Set Permissions & Ownership
    # We always enforce this to ensure consistency
    local_user = os.getenv("USER") or os.getenv("SUDO_USER")
    if not local_user:
        warning("Could not detect user, skipping chown.")
        return

    try:
        # Try changing ownership (requires sudo usually if not owned by user)
        # Optimization: Check stat first? No, just force ensure.
        cmd = ["chown", f"{local_user}:{local_user}", str(path)]
        execute_command(
            cmd, use_sudo=True, check=False
        )  # Warn but don't fail if user doesn't exist

        # Set Mode
        execute_command(["chmod", mode, str(path)], use_sudo=True)
    except Exception as e:
        warning(f"Failed to set permissions on {path}: {e}")


def prompt_for_confirmation(prompt_text: str, auto_confirm: bool = False) -> bool:
    if auto_confirm:
        info(f"'{prompt_text}'... (Auto-Confirmed)")
        return True

    while True:
        try:
            choice = input(f"❓ {prompt_text}? [Y/n]: ").strip().lower()
            if choice in ("y", "yes", ""):
                return True
            if choice in ("n", "no"):
                warning("❌ Operation cancelled by user.")
                return False
        except (KeyboardInterrupt, EOFError):
            print()  # New line
            warning("❌ Operation interrupted.")
            return False


T = TypeVar("T")


def prompt_for_choice(
    prompt: str,
    options: List[T],
    default: Optional[T] = None,
    auto_confirm: bool = False,
) -> T:
    """
    CLI Menu for selection.
    """
    if default is not None and default not in options:
        raise ValueError(f"Default '{default}' not in options: {options}")

    if auto_confirm:
        if default is None:
            # If no default but auto_confirm, pick first
            return options[0]
        info(f"{prompt} -> {default} (Auto)")
        return default

    # Display Menu
    print(f"\n🔍 {prompt}:")
    for idx, opt in enumerate(options, 1):
        is_default = " *" if opt == default else ""
        print(f"  {idx}. {opt}{is_default}")

    while True:
        try:
            sel = input(f"Select [1-{len(options)}]: ").strip()

            # Default on Enter
            if not sel and default is not None:
                return default

            idx = int(sel)
            if 1 <= idx <= len(options):
                choice = options[idx - 1]
                info(f"Selected: {choice}")
                return choice
            else:
                print(f"Invalid selection. Please enter 1-{len(options)}.")
        except ValueError:
            print("Please enter a number.")
        except (KeyboardInterrupt, EOFError):
            print()
            raise SystemExit("Aborted.")
