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

# Global brightness detection toggle
_brightness_detection_enabled = True

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

def calculate_image_brightness(image_bytes: bytes) -> float:
    """
    Calculate the average brightness of an image.
    Returns a value between 0-255 where 0 is completely dark and 255 is completely bright.
    """
    try:
        # Decode image from bytes
        nparr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return 0.0
        
        # Convert to grayscale for brightness calculation
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Calculate mean brightness
        brightness = np.mean(gray)
        
        return float(brightness)
        
    except Exception as e:
        print(f"Error calculating brightness: {e}")
        return 0.0

def is_image_too_dark(brightness: float, threshold: float = 30.0) -> bool:
    """
    Determine if an image is too dark based on brightness threshold.
    Default threshold is 30 (0-255 scale).
    """
    return brightness < threshold

@app.route("/detect", methods=["POST"])
def detect():
    """
    接收 JSON {image: base64, message: string (optional)}
    返回 JSON {cat: true/false, too_dark: true/false, brightness: float}
    并落库
    """
    data = request.get_json(force=True)
    if not data or "image" not in data:
        return jsonify({"cat": False, "too_dark": False, "error": "missing image"}), 400
    b64 = data["image"]
    esp32_message = data.get("message", "")  # Get message from ESP32 if provided
    
    # Display message if provided
    if esp32_message:
        print(f"[ESP32] Message: {esp32_message}")
    
    # 调整图片尺寸 - 最大尺寸320像素，保持宽高比
    try:
        image_bytes = base64.b64decode(b64)
        resized_bytes = resize_image_if_needed(image_bytes, max_size=320)
        # 将调整后的图片重新编码为base64用于检测
        resized_b64 = base64.b64encode(resized_bytes).decode('utf-8')
    except Exception as e:
        resized_b64 = b64  # 如果调整失败，使用原图
        resized_bytes = base64.b64decode(b64)
    
    # 计算图片亮度
    brightness = calculate_image_brightness(resized_bytes)
    
    # 根据全局设置决定是否检测亮度
    if _brightness_detection_enabled:
        too_dark = is_image_too_dark(brightness)
    else:
        too_dark = False  # 禁用亮度检测时，始终返回最大亮度
        brightness = 255.0  # 返回最大亮度值
    
    # 如果图片太暗，直接返回too_dark=true，不进行猫检测
    if too_dark:
        error_msg = f"Image too dark (brightness: {brightness:.2f})"
        if esp32_message:
            print(f"{error_msg} - {esp32_message} - skipping cat detection")
        else:
            print(f"{error_msg} - skipping cat detection")
        # 存图 - 使用递增序列ID
        img_id = get_next_image_id()
        img_name = f"{img_id:06d}.jpg"  # 6位数字，如 000001.jpg, 000002.jpg
        img_path = STATIC_DIR / img_name
        try:
            with open(img_path, "wb") as f:
                f.write(resized_bytes)
        except Exception as e:
            err = str(e)
        # Build message: append ESP32 message to error message
        message = error_msg
        if esp32_message:
            message += " | " + esp32_message
        db.insert_record(str(app.static_url_path + "/" + img_name), False, message)
        return jsonify({"cat": False, "too_dark": True, "brightness": brightness})
    
    # 使用调整后的图片进行检测
    cat, err = paddle_has_cat(resized_b64)
    
    # Always display detection result
    if esp32_message:
        print(f"[ESP32] Detection result: cat={cat}, message={esp32_message}")
    else:
        print(f"[ESP32] Detection result: cat={cat}")
    
    # 存图 - 使用递增序列ID
    img_id = get_next_image_id()
    img_name = f"{img_id:06d}.jpg"  # 6位数字，如 000001.jpg, 000002.jpg
    img_path = STATIC_DIR / img_name
    try:
        with open(img_path, "wb") as f:
            f.write(resized_bytes)
    except Exception as e:
        err = str(e)
    
    # Build message: start with error (if any), then append ESP32 message
    message = err if err else ""
    if esp32_message:
        if message:
            message += " | " + esp32_message
        else:
            message = esp32_message
    
    db.insert_record(str(app.static_url_path + "/" + img_name), cat, message)
    return jsonify({"cat": cat, "too_dark": False, "brightness": brightness})

@app.route("/toggle_brightness", methods=["POST"])
def toggle_brightness():
    """Toggle brightness detection on/off"""
    global _brightness_detection_enabled
    data = request.get_json(force=True)
    if "enabled" in data:
        _brightness_detection_enabled = bool(data["enabled"])
        print(f"Brightness detection {'enabled' if _brightness_detection_enabled else 'disabled'}")
        return jsonify({"success": True, "enabled": _brightness_detection_enabled})
    return jsonify({"success": False, "error": "missing enabled parameter"}), 400

@app.route("/brightness_status")
def brightness_status():
    """Get current brightness detection status"""
    global _brightness_detection_enabled
    return jsonify({"enabled": _brightness_detection_enabled})

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
    # 简单表格展示，包含亮度检测开关
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>猫检测记录</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .toggle-container { margin: 20px 0; padding: 15px; background: #f0f0f0; border-radius: 5px; }
            .toggle-switch { position: relative; display: inline-block; width: 60px; height: 34px; }
            .toggle-switch input { opacity: 0; width: 0; height: 0; }
            .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }
            .slider:before { position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
            input:checked + .slider { background-color: #2196F3; }
            input:checked + .slider:before { transform: translateX(26px); }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            img { max-width: 200px; height: auto; }
        </style>
    </head>
    <body>
        <h2>猫检测系统控制面板</h2>
        
        <div class="toggle-container">
            <h3>亮度检测控制</h3>
            <label class="toggle-switch">
                <input type="checkbox" id="brightnessToggle" onchange="toggleBrightness()">
                <span class="slider"></span>
            </label>
            <span id="toggleStatus">亮度检测: 启用</span>
        </div>
        
        <h3>最近 10 次检测记录（已自动清理旧记录）</h3>
        <table>
            <tr><th>时间</th><th>图片</th><th>有猫</th><th>消息</th></tr>
            {% for r in rows %}
            <tr>
                <td>{{ r.ts }}</td>
                <td><img src="{{ r.image_path }}" width="200"></td>
                <td>{{ "✔" if r.cat else "✘" }}</td>
                <td>{{ r.error or "-" }}</td>
            </tr>
            {% endfor %}
        </table>
        
        <script>
            // 页面加载时获取当前状态
            window.onload = function() {
                fetch('/brightness_status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('brightnessToggle').checked = data.enabled;
                        updateStatusText(data.enabled);
                    })
                    .catch(error => console.error('Error:', error));
            };
            
            function toggleBrightness() {
                const toggle = document.getElementById('brightnessToggle');
                const enabled = toggle.checked;
                
                fetch('/toggle_brightness', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({enabled: enabled})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        updateStatusText(data.enabled);
                        console.log('Brightness detection ' + (data.enabled ? 'enabled' : 'disabled'));
                    } else {
                        console.error('Failed to toggle brightness detection');
                        toggle.checked = !enabled; // 恢复原状态
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    toggle.checked = !enabled; // 恢复原状态
                });
            }
            
            function updateStatusText(enabled) {
                const statusText = document.getElementById('toggleStatus');
                statusText.textContent = '亮度检测: ' + (enabled ? '启用' : '禁用');
                statusText.style.color = enabled ? 'green' : 'red';
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False)