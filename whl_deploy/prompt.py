import sys

# Project support information
ISSUES_LINK = "https://github.com/ApolloAuto/apollo/issues"
SUPPORT_EMAIL = "support@wheelos.cn"


def print_help(error_message: str = None) -> None:
    """
    Prints concise help information for users, including issue tracker and support email.
    """
    print("\n" + "="*70)
    print("                 Encountered an Issue?")
    print("                We're Here to Help!")
    print("="*70)

    if error_message:
        print(f"\nError: {error_message}")

    print("\nPlease report issues at:")
    print(f"  GitHub: {ISSUES_LINK}")
    print(f"  Email:  {SUPPORT_EMAIL}")
    print("\nWhen reporting, please include software version, reproduction steps, and logs.")
    print("="*70 + "\n")

    if error_message:
        sys.exit(1)
