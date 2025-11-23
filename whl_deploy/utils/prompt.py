import sys


ISSUES_LINK = "https://github.com/wheelos/apollo-lite"
SUPPORT_EMAIL = "support@wheelos.cn"

ASCII_WHEELOS = r"""
           __              __
 _      __/ /_  ___  ___  / /___  _____
| | /| / / __ \/ _ \/ _ \/ / __ \/ ___/
| |/ |/ / / / /  __/  __/ / /_/ (__  )
|__/|__/_/ /_/\___/\___/_/\____/____/
"""


def build_welcome_text() -> str:
    """
    Build the welcome banner text including ASCII art and contact info.
    """
    lines = [
        ASCII_WHEELOS,
        "",
        f"GitHub: {ISSUES_LINK}",
        f"Email : {SUPPORT_EMAIL}",
        "",
    ]
    return "\n".join(lines)


def show_welcome() -> None:
    """
    Display the welcome banner to the user.
    """
    banner = build_welcome_text()
    print(banner)


if __name__ == "__main__":
    show_welcome()
