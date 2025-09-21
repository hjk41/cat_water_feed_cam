import base64
import requests
from pathlib import Path


BASE_URL = "http://127.0.0.1:8099"  # Update if your server runs on a different host/port
TEST_IMAGE_PATH = Path("2.jpg")

if __name__ == "__main__":
    # Ensure the test image exists
    if not TEST_IMAGE_PATH.exists():
        print("Test image not found!")
        exit(1)

    # Read and encode the image in base64
    with open(TEST_IMAGE_PATH, "rb") as img_file:
        b64_image = base64.b64encode(img_file.read()).decode("utf-8")

    # Prepare the payload
    payload = {"image": b64_image}

    # Send the POST request to the /detect endpoint
    response = requests.post(f"{BASE_URL}/detect", json=payload)

    # Check the response status code
    if response.status_code == 200:
        response_json = response.json()
        print("Response:", response_json)
    else:
        print(f"Failed to upload image. Status code: {response.status_code}")
        print("Response:", response.text)