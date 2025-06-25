import logging
import os
import subprocess
import sys
from typing import List, Optional, Dict

# --- Setup Logging ---
# Configure logging to output to stderr with color


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add color to log messages."""
    COLORS = {
        'INFO': '\033[34m\033[1m',  # Blue bold
        'WARNING': '\033[33m\033[1m',  # Yellow bold
        'ERROR': '\033[31m\033[1m',  # Red bold
        'CRITICAL': '\033[31m\033[1m',  # Red bold
        'RESET': '\033[0m'
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
formatter = ColoredFormatter('%(message)s')
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set default logging level
logger.addHandler(handler)

# Override default logging methods with custom names for convenience
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
    use_sudo: bool = True,
    input_data: Optional[bytes] = None
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

    if use_sudo and os.geteuid() != 0:
        cmd_to_execute.insert(0, "sudo")

    info(f"Executing: {' '.join(cmd_to_execute)}")

    try:
        result = subprocess.run(
            cmd_to_execute,
            capture_output=capture_output,
            text=text,
            input=input_data,
            check=False  # We handle checking explicitly
        )

        if result.stdout and capture_output:
            for line in result.stdout.splitlines():
                info(f"STDOUT: {line.strip()}")
        if result.stderr and capture_output:
            for line in result.stderr.splitlines():
                info(f"STDERR: {line.strip()}")

        if check and result.returncode != 0:
            raise CommandExecutionError(
                f"Command failed with exit code {result.returncode}",
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )
        return result
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Command not found: '{command[0]}'. Please ensure it is installed and in your PATH.")
    except Exception as e:
        error(
            f"An unexpected error occurred while executing '{' '.join(cmd_to_execute)}': {e}")
        raise


def execute_docker_command(
    command_args: List[str],
    capture_output: bool = True,
    text: bool = True,
    check: bool = True,
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Wrapper for executing Docker commands. Automatically prepends 'sudo docker'.
    """
    full_command = ["sudo", "docker"] + command_args
    return execute_command(full_command, capture_output, text, check, **kwargs)


def get_os_info() -> Dict[str, str]:
    """
    Gets OS distribution and codename.
    (This function is identical to the one in the optimized Docker script)
    """
    info("Attempting to get OS information...")
    os_info = {}
    try:
        lsb_id = execute_command(["lsb_release", "-is"], capture_output=True,
                                 text=True, check=True, use_sudo=False).stdout.strip().lower()
        lsb_codename = execute_command(["lsb_release", "-cs"], capture_output=True,
                                       text=True, check=True, use_sudo=False).stdout.strip().lower()
        os_info['id'] = lsb_id
        os_info['codename'] = lsb_codename
        info(
            f"OS Info (lsb_release): ID={os_info.get('id')}, Codename={os_info.get('codename')}")
    except (FileNotFoundError, CommandExecutionError):
        info("lsb_release not found or failed, falling back to /etc/os-release.")
        try:
            with open("/etc/os-release", 'r') as f:
                for line in f:
                    if line.startswith("ID="):
                        os_info['id'] = line.strip().split(
                            '=')[1].strip('"').lower()
                    elif line.startswith("VERSION_CODENAME="):
                        os_info['codename'] = line.strip().split('=')[
                            1].strip('"').lower()
            info(
                f"OS Info (/etc/os-release): ID={os_info.get('id')}, Codename={os_info.get('codename')}")
        except FileNotFoundError:
            raise RuntimeError(
                "Could not determine OS distribution. Neither lsb_release nor /etc/os-release found.")
    return os_info
