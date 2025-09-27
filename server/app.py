import os
import base64
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, url_for
import requests
import database as db
from dotenv import load_dotenv
from detection import paddle_has_cat_from_b64 as paddle_has_cat

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
    cat, err = paddle_has_cat(b64)
    # 存图 - 使用递增序列ID
    img_id = get_next_image_id()
    img_name = f"{img_id:06d}.jpg"  # 6位数字，如 000001.jpg, 000002.jpg
    img_path = STATIC_DIR / img_name
    try:
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64))
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