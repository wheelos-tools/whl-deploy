import requests
import socket


def can_access_github():
    """
    Checks if https://github.com/ is accessible.
    Returns True if accessible, False otherwise.
    """
    url = "https://github.com/"
    try:
        # Set a short timeout to prevent hanging indefinitely
        response = requests.get(url, timeout=5)

        # Check the HTTP status code; 200 indicates success
        if response.status_code == 200:
            return True
        else:
            # If status code is not 200, consider it a failed access
            print(f"Failed to access GitHub. Status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError as e:
        # Catch connection errors (e.g., DNS resolution failure, network unreachable)
        print(f"Connection error: {e}")
        return False
    except requests.exceptions.Timeout as e:
        # Catch timeout errors (request took too long)
        print(f"Timeout error: {e}")
        return False
    except requests.exceptions.RequestException as e:
        # Catch any other requests-related exceptions
        print(f"An unexpected request error occurred: {e}")
        return False
    except socket.gaierror as e:
        # Catch DNS resolution errors (often nested within ConnectionError but good to be explicit)
        print(f"DNS resolution error: {e}")
        return False
    except Exception as e:
        # Catch any other unforeseen errors
        print(f"An unexpected error occurred: {e}")
        return False
