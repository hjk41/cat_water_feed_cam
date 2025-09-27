import base64
import requests
from pathlib import Path


BASE_URL = "http://127.0.0.1:8099"  # Update if your server runs on a different host/port

if __name__ == "__main__":
    test_dir = Path(__file__).parent
    jpg_files = sorted(test_dir.glob("*.jpg"))

    if not jpg_files:
        print("No .jpg files found in", test_dir)
        exit(1)

    for img_path in jpg_files:
        try:
            with open(img_path, "rb") as img_file:
                b64_image = base64.b64encode(img_file.read()).decode("utf-8")
            payload = {"image": b64_image}
            response = requests.post(f"{BASE_URL}/detect", json=payload, timeout=30)
            if response.status_code == 200:
                print(f"{img_path.name} -> {response.json()}")
            else:
                print(f"{img_path.name} -> HTTP {response.status_code}: {response.text}")
        except Exception as e:
            print(f"{img_path.name} -> ERROR: {e}")