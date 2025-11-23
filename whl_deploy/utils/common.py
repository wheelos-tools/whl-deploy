import logging
import os
import subprocess
import sys
from typing import List, Optional, Dict, Union, TypeVar
from pathlib import Path

# --- Setup Logging ---
# Configure logging to output to stderr with color


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add color to log messages."""

    COLORS = {
        "INFO": "\033[34m\033[1m",  # Blue bold
        "WARNING": "\033[33m\033[1m",  # Yellow bold
        "ERROR": "\033[31m\033[1m",  # Red bold
        "CRITICAL": "\033[31m\033[1m",  # Red bold
        "RESET": "\033[0m",
    }

    def format(self, record):
        log_message = super().format(record)
        return f"[{self.COLORS.get(record.levelname, '')}{record.levelname}{self.COLORS['RESET']}] {log_message}"


# Remove default handlers if any
if logging.root.handlers:
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)

# Setup a new handler for stderr
handler = logging.StreamHandler(sys.stderr)
formatter = ColoredFormatter("%(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set default logging level
logger.addHandler(handler)

# Override default logging methods with custom names for convenience
debug = logger.debug
info = logger.info
warning = logger.warning
error = logger.error
critical = logger.critical

# --- Custom Exception for Command Execution Errors ---


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
    input_data: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    """
    Executes a shell command using subprocess.run.

    Args:
        command: The command and its arguments as a list of strings.
        check: If True, raises CommandExecutionError for non-zero exit codes.
        capture_output: If True, stdout and stderr are captured.
        text: If True, stdout and stderr are decoded as text.
        use_sudo: If True, prepends 'sudo' to the command if not already root.
        input_data: Optional bytes data to pass to stdin.

    Returns:
        A subprocess.CompletedProcess object.

    Raises:
        CommandExecutionError: If 'check' is True and command fails.
        FileNotFoundError: If the command executable is not found.
    """
    cmd_to_execute = list(command)  # Create a mutable copy

    if use_sudo:
        cmd_to_execute.insert(0, "sudo")

    debug(f"Executing: {' '.join(cmd_to_execute)}")

    try:
        result = subprocess.run(
            cmd_to_execute,
            capture_output=capture_output,
            text=text,
            input=input_data,
            check=False,  # We handle checking explicitly
        )

        # if result.stdout and capture_output:
        #     for line in result.stdout.splitlines():
        #         info(f"STDOUT: {line.strip()}")
        if result.stderr and capture_output:
            for line in result.stderr.splitlines():
                info(f"STDERR: {line.strip()}")

        if check and result.returncode != 0:
            raise CommandExecutionError(
                f"Command failed with exit code {result.returncode}",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Command not found: '{command[0]}'. Please ensure it is installed and in your PATH."
        )
    except Exception as e:
        error(
            f"An unexpected error occurred while executing '{' '.join(cmd_to_execute)}': {e}"
        )
        raise


def execute_docker_command(
    command_args: List[str],
    capture_output: bool = True,
    text: bool = True,
    check: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """
    Wrapper for executing Docker commands. Automatically prepends 'sudo docker'.
    """
    full_command = ["docker"] + command_args
    print(full_command)
    return execute_command(full_command, capture_output, text, check, **kwargs)


def get_os_info() -> Dict[str, str]:
    """
    Gets OS distribution and codename.
    (This function is identical to the one in the optimized Docker script)
    """
    os_info = {}
    try:
        lsb_id = (
            execute_command(
                ["lsb_release", "-is"],
                capture_output=True,
                text=True,
                check=True,
                use_sudo=False,
            )
            .stdout.strip()
            .lower()
        )
        lsb_codename = (
            execute_command(
                ["lsb_release", "-cs"],
                capture_output=True,
                text=True,
                check=True,
                use_sudo=False,
            )
            .stdout.strip()
            .lower()
        )
        os_info["id"] = lsb_id
        os_info["codename"] = lsb_codename
        debug(
            f"OS Info (lsb_release): ID={os_info.get('id')}, Codename={os_info.get('codename')}"
        )
    except (FileNotFoundError, CommandExecutionError):
        info("lsb_release not found or failed, falling back to /etc/os-release.")
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("ID="):
                        os_info["id"] = line.strip().split("=")[1].strip('"').lower()
                    elif line.startswith("VERSION_CODENAME="):
                        os_info["codename"] = (
                            line.strip().split("=")[1].strip('"').lower()
                        )
            debug(
                f"OS Info (/etc/os-release): ID={os_info.get('id')}, Codename={os_info.get('codename')}"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Could not determine OS distribution. Neither lsb_release nor /etc/os-release found."
            )
    return os_info


def ensure_dir(t_dir: Union[str, Path]) -> None:
    resolved_path = Path(t_dir).resolve()

    info(
        f"Ensuring cache directory '{resolved_path}' exists and has correct permissions..."
    )

    # 1. Check if the directory already exists
    directory_already_exists = False
    try:
        # 'test -d' checks if path exists and is a directory.
        # It typically doesn't require sudo unless parent directories are inaccessible.
        execute_command(
            ["test", "-d", str(resolved_path)], check=True, capture_output=True
        )
        # If 'test -d' succeeds (return code 0), the directory exists
        directory_already_exists = True
        info(f"Directory '{resolved_path}' already exists.")
    except CommandExecutionError:
        # 'test -d' failed, meaning the directory does not exist or is not a directory
        info(f"Directory '{resolved_path}' does not exist or is not a directory.")
        # Explicitly set to false in case of previous partial success
        directory_already_exists = False

    # 2. Create the directory if it doesn't exist
    if not directory_already_exists:
        try:
            info(f"Creating cache directory '{resolved_path}'...")
            # 'mkdir -p' creates parent directories as needed and does not error if dir exists.
            execute_command(["mkdir", "-p", str(resolved_path)], use_sudo=True)
            info(f"Cache directory '{resolved_path}' created successfully.")
        except CommandExecutionError as e:
            # Catch the specific command execution error
            error(f"Failed to create cache directory '{resolved_path}': {e}.")
            raise CommandExecutionError(
                f"Failed to create cache directory '{resolved_path}': {e}. "
                "Please check permissions for path or parent directories."
            )
        except Exception as e:
            # Catch any other unexpected errors during directory creation
            critical(
                f"An unexpected error occurred while creating directory '{resolved_path}': {e}",
                exc_info=True,
            )
            raise

    # 3. Set permissions for the directory
    # Use 0o775 (rwxrwxr-x): read/write/execute for owner and group, read/execute for others.
    # This is suitable for shared directories where different users (e.g., build system users)
    # might need access.
    permission_mode = "0775"
    local_user = os.getenv("USER")
    try:
        info(f"Setting permissions {permission_mode} for '{resolved_path}'...")
        # 'chmod' may require sudo if the directory is owned by root or another user.
        execute_command(["chmod", permission_mode, str(resolved_path)], use_sudo=True)
        execute_command(
            ["chown", f"{local_user}:{local_user}", str(resolved_path)], use_sudo=True
        )
        info(
            f"Cache directory '{resolved_path}' is prepared with permissions {permission_mode}."
        )
    except CommandExecutionError as e:
        # Catch the specific command execution error
        error(f"Failed to set permissions for '{resolved_path}': {e}.")
        raise CommandExecutionError(
            f"Failed to set permissions for '{resolved_path}': {e}. "
            "Please ensure the user running this script has appropriate privileges (e.g., sudo)."
        )
    except Exception as e:
        # Catch any other unexpected errors during permission setting
        critical(
            f"An unexpected error occurred while setting permissions for '{resolved_path}': {e}",
            exc_info=True,
        )
        raise


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


T = TypeVar("T")


def prompt_for_choice(
    prompt: str,
    options: List[T],
    default: Optional[T] = None,
    auto_confirm: bool = False,
) -> T:
    """
    Prompt user with a single-line style menu choice.

    :param prompt: prompt message, e.g. "Select mirror"
    :param options: list of options
    :param default: default option (must be in options)
    :param auto_confirm: if True, immediately return default
    :return: the selected option
    """
    if default is not None and default not in options:
        raise ValueError("default must be one of the options")
    if auto_confirm:
        if default is None:
            raise ValueError("default required when auto_confirm is True")
        print(f"{prompt} -> {default} (auto)")
        return default

    # Build a compact, one-line prompt string
    opts = ", ".join(f"{i}:{opt}" for i, opt in enumerate(options, start=1))
    default_index = options.index(default) + 1 if default is not None else None
    default_hint = f"[{default_index}]" if default_index else ""
    full_prompt = f"{prompt} ({opts}) {default_hint}: "

    while True:
        try:
            sel = input(full_prompt).strip()
            if sel == "":
                if default is not None:
                    return default
                # no default, but no input — ask again
                print("No choice given.")
                continue

            # try parse number
            try:
                idx = int(sel)
            except ValueError:
                print("Invalid input. Enter number.")
                continue

            if 1 <= idx <= len(options):
                return options[idx - 1]
            else:
                print(f"Out of range: 1 to {len(options)}.")

        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(1)
        except EOFError:
            print("\nNo input, exit.")
            sys.exit(1)
