import os
import base64
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, url_for
import requests
import database as db
from dotenv import load_dotenv
from dashscope import MultiModalConversation

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
STATIC_DIR = Path("static/record")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# ========== 通义千问 API 配置 ==========
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY environment variable is not set.")
# ======================================

def qwen_has_cat(b64_image: str) -> (bool, str):
    """
    调用通义千问视觉模型，返回 (是否检测到猫, 错误信息)
    这里用通用检测 + 后过滤 label==cat
    """
    try:
        image_data = base64.b64decode(b64_image)
        image_path = f"data:image/jpeg;base64,{b64_image}" #f"file://{local_path}" #  Use data URI directly

        messages = [
            {
                "role": "user",
                "content": [
                    {"image": image_path},
                    {"text": "图中是否有猫？请直接回答 有 或 没有。"}
                ]
            }
        ]

        response = MultiModalConversation.call(
            api_key=DASHSCOPE_API_KEY,
            model='qwen-vl-plus',
            messages=messages,
            stream=False,
            result_format='json'
        )

        if response["status_code"] != 200:
            return False, f"Qwen API {response['status_code']}: {response['message']}"

        answer = response["output"]["choices"][0]["message"]["content"][0]["text"]
        return not "没有" in answer, ""

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
    cat, err = qwen_has_cat(b64)
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
    查看最近 20 次调用记录
    """
    rows = db.get_recent_logs()
    for r in rows:
        r['image_path'] = r['image_path'].replace('\\\\', '/').replace('\\', '/')
    # 简单表格展示
    html = """
    <h2>最近 20 次检测记录</h2>
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