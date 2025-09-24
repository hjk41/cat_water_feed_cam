import os
import base64
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, url_for
import requests
import database as db
from dotenv import load_dotenv
import numpy as np
import cv2

# PaddleClas will be imported lazily to speed up initial import
_paddle_clas_model = None

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
STATIC_DIR = Path("static/record")
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def _get_paddle_clas():
    """Lazy init and return PaddleClas classifier instance."""
    global _paddle_clas_model
    if _paddle_clas_model is None:
        try:
            from paddleclas import PaddleClas
        except Exception as e:
            raise RuntimeError(f"Failed to import PaddleClas: {e}")
        # Use CPU by default; set use_gpu=True if GPU is available and configured
        _paddle_clas_model = PaddleClas(topk=5, use_gpu=False)
    return _paddle_clas_model


from typing import Tuple

def paddle_has_cat(b64_image: str) -> Tuple[bool, str]:
    """
    使用本地 PaddleClas 进行图像分类，判断是否包含猫类。
    规则：预测 Top-K 类别名中包含 'cat'/'kitten'/'lynx'/'tiger cat' 等即视为有猫。
    返回 (是否检测到猫, 错误信息)。
    """
    try:
        image_bytes = base64.b64decode(b64_image)
        nparr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, "failed to decode image"

        classifier = _get_paddle_clas()
        results = classifier.predict(img)
        # results is typically a list with one dict for the input image
        # Example keys: 'class_ids', 'scores', 'label_names'
        has_cat = False
        if isinstance(results, list) and len(results) > 0 and isinstance(results[0], dict):
            labels = results[0].get("label_names") or []
            labels_lc = [str(x).lower() for x in labels]
            cat_keywords = [
                "cat", "kitten", "tomcat", "tabby", "tiger cat", "siamese", "persian",
                "egyptian cat", "lynx", "wildcat"
            ]
            has_cat = any(any(k in lbl for k in cat_keywords) for lbl in labels_lc)
        else:
            # Fallback: stringify results and search keywords
            text = str(results).lower()
            has_cat = any(k in text for k in ["cat", "kitten", "tiger cat", "lynx", "wildcat"]) 

        return has_cat, ""
    except Exception as e:
        return False, str(e)

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
    # 存图
    img_name = f"{uuid.uuid4().hex}.jpg"
    img_path = STATIC_DIR / img_name
    try:
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64))
    except Exception as e:
        err = str(e)
    db.insert_record(str(img_path), cat, err)
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
        <td><img src="/{{ r.image_path }}" width="200"></td>
        <td>{{ "✔" if r.cat else "✘" }}</td>
        <td>{{ r.error or "-" }}</td>
      </tr>
      {% endfor %}
    </table>
    """
    return render_template_string(html, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False)