# 智能猫咪饮水器 (Smart Cat Water Feeder)

一个基于ESP32-CAM和AI检测的自动猫咪饮水器系统，能够智能识别猫咪并自动控制饮水机开关。

## 项目概述

这个项目包含两个主要组件：
- **ESP32-CAM模块**：负责红外感应、拍照和饮水机控制
- **服务器模块**：负责AI图像识别和检测记录管理

## 系统架构

```
ESP32-CAM (硬件) ←→ WiFi ←→ Flask服务器 (AI检测)
     ↓
PIR传感器 → 拍照 → 发送图片 → AI检测 → 控制饮水机
```

## 功能特性

- 🔍 **智能检测**：使用PaddleClas AI模型识别猫咪
- 📸 **自动拍照**：PIR传感器触发后每10秒拍照检测
- 💧 **自动控制**：检测到猫咪时自动开启饮水机
- 📊 **记录管理**：自动保存检测记录和图片
- 🧹 **自动清理**：只保留最近10条记录，自动清理旧数据
- 🌐 **Web界面**：通过浏览器查看检测历史

## 硬件要求

### ESP32-CAM模块
- ESP32-CAM开发板
- PIR红外传感器 (接GPIO15)
- 饮水机继电器控制模块 (接GPIO12,13)
- LED指示灯 (使用板载LED，GPIO4)

### 接线说明
```
PIR传感器 → GPIO15 (上拉输入)
饮水机正极控制 → GPIO12
饮水机负极控制 → GPIO13
LED指示灯 → GPIO4 (板载LED)
```

## 软件要求

### ESP32-CAM端
- Arduino IDE
- ESP32开发板支持包
- 所需库：WiFi, HTTPClient, base64

### 服务器端
- Python 3.7+
- Flask 2.3.3
- PaddlePaddle 2.6.2
- PaddleClas
- OpenCV

## 安装和配置

### 1. ESP32-CAM配置

1. 安装Arduino IDE和ESP32开发板支持包
2. 安装所需库：
   ```
   WiFi (ESP32内置)
   HTTPClient (ESP32内置)
   base64 (ESP32内置)
   ```
3. 创建`wifi_config.h`文件，配置WiFi信息：
   ```cpp
   const char* ssid = "你的WiFi名称";
   const char* password = "你的WiFi密码";
   const char* serverUrl = "http://服务器IP:8099/detect";
   ```
4. 上传代码到ESP32-CAM

### 2. 服务器配置

1. 安装Python依赖：
   ```bash
   cd server
   pip install -r requirements.txt
   ```

2. 初始化数据库：
   ```bash
   python database.py
   ```

3. 启动服务器：
   ```bash
   python app.py
   ```

服务器将在`http://0.0.0.0:8099`启动

## 使用方法

### 启动系统
1. 确保ESP32-CAM和服务器在同一WiFi网络
2. 启动Flask服务器
3. 给ESP32-CAM上电
4. 系统将自动开始工作

### 工作流程
1. PIR传感器检测到运动
2. ESP32-CAM拍照并发送到服务器
3. 服务器使用AI模型检测图片中是否有猫
4. 如果检测到猫，开启饮水机；否则关闭
5. 每10秒重复检测，直到没有检测到猫
6. 记录保存到数据库和静态文件

### 查看检测记录
访问 `http://服务器IP:8099/log` 查看最近的检测记录

## API接口

### POST /detect
接收图片并返回检测结果

**请求格式：**
```json
{
  "image": "base64编码的图片数据"
}
```

**响应格式：**
```json
{
  "cat": true/false
}
```

### GET /log
查看检测历史记录

## 配置说明

### 检测参数
- 检测间隔：10秒
- 图片尺寸：最大640像素（自动调整）
- 记录保留：最近10条记录
- 无触发超时：30秒后关闭饮水机

### 硬件参数
- PIR触发：高电平
- 饮水机控制：500ms脉冲
- LED指示：检测时亮起

## 故障排除

### 常见问题

1. **WiFi连接失败**
   - 检查WiFi配置是否正确
   - 确保网络信号良好

2. **检测不准确**
   - 调整摄像头位置和角度
   - 确保光线充足
   - 检查PIR传感器灵敏度

3. **饮水机不工作**
   - 检查继电器接线
   - 确认饮水机电源
   - 检查GPIO配置

4. **服务器连接失败**
   - 检查服务器IP地址
   - 确认端口8099可访问
   - 检查防火墙设置

### 调试信息
ESP32-CAM会通过串口输出详细的调试信息，波特率115200。

## 项目结构

```
cat_water_feed/
├── cam/
│   └── sketch_sep21a/
│       └── sketch_sep21a.ino    # ESP32-CAM主程序
├── server/
│   ├── app.py                   # Flask服务器主程序
│   ├── detection.py             # AI检测模块
│   ├── database.py              # 数据库操作
│   ├── requirements.txt         # Python依赖
│   ├── static/                  # 图片存储目录
│   └── test/                    # 测试文件
├── detect.db                    # SQLite数据库
└── readme.md                    # 项目说明
```

## 技术栈

- **硬件**：ESP32-CAM, PIR传感器, 继电器模块
- **嵌入式**：Arduino C++, ESP32框架
- **后端**：Python, Flask, SQLite
- **AI**：PaddlePaddle, PaddleClas
- **图像处理**：OpenCV, NumPy

## 许可证

本项目采用MIT许可证。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 更新日志

- v1.0.0: 初始版本，支持基本的猫咪检测和饮水机控制
- 支持PIR触发检测
- 集成PaddleClas AI模型
- 自动记录管理和清理
- Web界面查看历史记录
