import requests
from utils import api_base_url


def check_user_exists(username):
    url = f"https://{api_base_url}/check_user"

    params = {"username": username, "API-Key": "apikeyhaha"}
    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        return data["exists"]
    print(f"Error: Unable to check user. Status code: {response.status_code}")
    return False


def check_if_exists(username):
    user_exists = check_user_exists(username)
    if user_exists is not None:
        print(f"User '{username}' exists: {user_exists}")
        return user_exists
    print("Failed to check user existence.")
    return False
