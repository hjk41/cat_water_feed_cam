import base64
import sys
from pathlib import Path

# Ensure parent directory (server/) is on path so we can import detection.py
sys.path.append(str(Path(__file__).resolve().parents[1]))

from detection import paddle_has_cat_from_bytes


if __name__ == "__main__":
    test_dir = Path(__file__).parent
    jpg_files = sorted(test_dir.glob("*.jpg"))

    if not jpg_files:
        print("No .jpg files found in", test_dir)
        raise SystemExit(1)

    for img_path in jpg_files:
        try:
            data = img_path.read_bytes()
            cat, err = paddle_has_cat_from_bytes(data)
            if err:
                print(f"{img_path.name} -> ERROR: {err}")
            else:
                print(f"{img_path.name} -> cat: {cat}")
        except Exception as e:
            print(f"{img_path.name} -> EXCEPTION: {e}")

