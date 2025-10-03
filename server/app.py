import os
import base64
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, url_for
import requests
import database as db
from dotenv import load_dotenv
from detection import paddle_has_cat_from_b64 as paddle_has_cat
import cv2
import numpy as np

load_dotenv()  # Load environment variables from .env file

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='/static')

# Global counter for incremental image IDs
_image_counter = 0

def initialize_image_counter():
    """Initialize the image counter based on existing files"""
    global _image_counter
    max_id = 0
    if STATIC_DIR.exists():
        for file_path in STATIC_DIR.glob("*.jpg"):
            try:
                # Extract numeric ID from filename (e.g., "000001.jpg" -> 1)
                file_id = int(file_path.stem)
                max_id = max(max_id, file_id)
            except ValueError:
                # Skip files that don't match the numeric pattern
                continue
    if max_id >= (100000 - 1):
        max_id = 0
    _image_counter = max_id

def get_next_image_id():
    """Get the next incremental image ID"""
    global _image_counter
    _image_counter += 1
    return _image_counter

# Initialize counter on startup
initialize_image_counter()

def resize_image_if_needed(image_bytes: bytes, max_size: int = 640) -> bytes:
    """
    Resize image to at most max_size in the largest dimension while keeping aspect ratio.
    Image is already flipped by ESP32, so no additional flipping needed.
    Returns the resized image as bytes.
    """
    try:
        # Decode image from bytes
        nparr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return image_bytes  # Return original if decode fails
        
        height, width = img.shape[:2]
        
        # Calculate new dimensions
        if max(height, width) <= max_size:
            # No resize needed, just encode the image
            _, encoded_img = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return encoded_img.tobytes()
        
        # Calculate scale factor
        scale = max_size / max(height, width)
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        # Resize image
        resized_img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # Encode back to bytes
        _, encoded_img = cv2.imencode('.jpg', resized_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded_img.tobytes()
        
    except Exception:
        # Return original image if resize fails
        return image_bytes

from typing import Tuple

@app.route("/detect", methods=["POST"])
def detect():
    """
    接收 JSON {image: base64}
    返回 JSON {cat: true/false}
    并落库
    """
    data = request.get_json(force=True)
    if not data or "image" not in data:
        return jsonify({"cat": False, "error": "missing image"}), 400
    b64 = data["image"]
    
    # 调整图片尺寸 - 最大尺寸640像素，保持宽高比
    try:
        image_bytes = base64.b64decode(b64)
        resized_bytes = resize_image_if_needed(image_bytes, max_size=640)
        # 将调整后的图片重新编码为base64用于检测
        resized_b64 = base64.b64encode(resized_bytes).decode('utf-8')
    except Exception as e:
        resized_b64 = b64  # 如果调整失败，使用原图
        resized_bytes = base64.b64decode(b64)
    
    # 使用调整后的图片进行检测
    cat, err = paddle_has_cat(resized_b64)
    
    # 存图 - 使用递增序列ID
    img_id = get_next_image_id()
    img_name = f"{img_id:06d}.jpg"  # 6位数字，如 000001.jpg, 000002.jpg
    img_path = STATIC_DIR / img_name
    try:
        with open(img_path, "wb") as f:
            f.write(resized_bytes)
    except Exception as e:
        err = str(e)
    db.insert_record(str(app.static_url_path + "/" + img_name), cat, err)
    return jsonify({"cat": cat})

@app.route("/log")
def log():
    """
    查看最近 10 次调用记录，并清理更旧的记录与文件
    """
    # Clean DB and FS: keep only last 10
    try:
        deleted = db.delete_older_records_keep_latest(limit=10)
        for item in deleted:
            try:
                p = Path(item["image_path"]) if item.get("image_path") else None
                if p and p.exists():
                    p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        # Ignore cleanup errors for log page availability
        deleted = []

    rows = db.get_recent_logs(limit=10)
    for r in rows:
        r['image_path'] = r['image_path'].replace('\\\\', '/').replace('\\', '/')
    # 简单表格展示
    html = """
    <h2>最近 10 次检测记录（已自动清理旧记录）</h2>
    <table border="1" cellpadding="5">
      <tr><th>时间</th><th>图片</th><th>有猫</th><th>错误</th></tr>
      {% for r in rows %}
      <tr>
        <td>{{ r.ts }}</td>
        <td><img src="{{ r.image_path }}" width="200"></td>
        <td>{{ "✔" if r.cat else "✘" }}</td>
        <td>{{ r.error or "-" }}</td>
      </tr>
      {% endfor %}
    </table>
    """
    return render_template_string(html, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False)