import requests
from typing import Optional

# --- Function to get public IP ---
def get_public_ip() -> Optional[str]:
    """
    Retrieves the public IP address of the local machine.
    This function also uses the requests library to access a simple online service
    to determine the IP.
    """
    try:
        response = requests.get("https://api.ipify.org", timeout=5)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        return response.text.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error getting public IP: {e}")
        return None

# --- IP Country Code Lookup Function ---
def get_ip_country_code(ip_address: Optional[str] = None) -> Optional[str]:
    """
    Retrieves the country code for a given IP address using an online IP geolocation API.
    This function primarily uses the requests library for network requests.

    Args:
        ip_address: The IP address to query. If None, it attempts to retrieve the
                    public IP of the local machine.
                    For server-side applications, client IP is usually obtained from
                    request headers (e.g., Flask's request.remote_addr or X-Forwarded-For).
    Returns:
        The ISO 3166-1 alpha-2 country code (e.g., "CN", "US", "JP"),
        or None if the query fails or no country information is found for the IP.
    """
    if ip_address is None:
        ip_address = get_public_ip() # Attempt to get the public egress IP of the local machine
        if ip_address is None:
            print("Could not determine IP address for online query.")
            return None

    try:
        # Using ip-api.com as an example API.
        # The 'fields' parameter specifies to return only 'countryCode', 'status', and 'message'
        # to reduce data transfer.
        api_url = f"http://ip-api.com/json/{ip_address}?fields=countryCode,status,message"
        print(f"Querying IP location for {ip_address} using {api_url}...")

        # Send HTTP GET request
        response = requests.get(api_url, timeout=5) # Set a timeout to prevent indefinite waiting
        response.raise_for_status() # Raises an HTTPError if the response status code is 4xx or 5xx

        # Parse the JSON response
        data = response.json()

        if data.get("status") == "success":
            country_code = data.get("countryCode")
            print(f"IP {ip_address} is located in {country_code}.")
            return country_code
        else:
            # The API might return a "fail" status with an error message
            message = data.get("message", "Unknown error from API")
            print(f"IP API query failed for {ip_address}: {message}")
            return None
    except requests.exceptions.RequestException as e:
        # Catch all requests-related exceptions, including connection errors, timeouts, HTTP errors, etc.
        print(f"Network or HTTP error during IP lookup for {ip_address}: {e}")
        return None
    except ValueError:
        # If the response is not valid JSON
        print(f"Invalid JSON response received from IP API for {ip_address}.")
        return None
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred during online IP lookup for {ip_address}: {e}")
        return None
