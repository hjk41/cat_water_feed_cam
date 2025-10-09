# Smart Cat Water Feeder

An intelligent cat water feeder system based on ESP32-CAM and AI detection that can automatically identify cats and control the water dispenser.

## Project Overview

This project consists of two main components:
- **ESP32-CAM Module**: Handles PIR sensing, image capture, and water dispenser control
- **Server Module**: Handles AI image recognition and detection record management

## System Architecture

```
ESP32-CAM (Hardware) ←→ WiFi ←→ Flask Server (AI Detection)
     ↓
PIR Sensor → Capture Image → Send Image → AI Detection → Control Water Dispenser
```

## Features

- 🔍 **Smart Detection**: Uses PaddleClas AI model to identify cats
- 📸 **Auto Capture**: Takes photos every 10 seconds after PIR sensor trigger
- 💧 **Auto Control**: Automatically turns on water dispenser when cat is detected
- 🌙 **Dark Image Detection**: Automatically detects and skips processing of dark images
- 🔄 **Toggle Control**: Web-based toggle switch to enable/disable brightness detection
- 📊 **Record Management**: Automatically saves detection records and images
- 🧹 **Auto Cleanup**: Keeps only the latest 10 records, automatically cleans old data
- 🌐 **Web Interface**: View detection history through browser with control panel

## Hardware Requirements

### ESP32-CAM Module
- ESP32-CAM development board
- PIR infrared sensor (connected to GPIO15)
- Water dispenser relay control module (connected to GPIO12,13)
- LED indicator (using onboard LED, GPIO4)

### Chassis Design
A custom chassis has been designed in OnShape to house the ESP32-CAM and HC-SR501 PIR detector:
**[OnShape Chassis Design](https://cad.onshape.com/documents/1c71ee66375d04679ef608ec/v/df9be5f772127def05042a16/e/46879c1adbf0714d15114029?renderMode=0&uiState=68e72e921494860b01941a11)**

### Wiring Diagram
```
PIR Sensor → GPIO15 (pull-up input)
Water Dispenser Positive Control → GPIO12
Water Dispenser Negative Control → GPIO13
LED Indicator → GPIO4 (onboard LED)
```

## Software Requirements

### ESP32-CAM Side
- Arduino IDE
- ESP32 board support package
- Required libraries: WiFi, HTTPClient, base64

### Server Side
- Python 3.7+
- Flask 2.3.3
- PaddlePaddle 2.6.2
- PaddleClas
- OpenCV

## Installation and Configuration

### 1. ESP32-CAM Configuration

1. Install Arduino IDE and ESP32 board support package
2. Install required libraries:
   ```
   WiFi (built-in ESP32)
   HTTPClient (built-in ESP32)
   base64 (built-in ESP32)
   ```
3. Create `wifi_config.h` file and configure WiFi information:
   ```cpp
   const char* ssid = "Your WiFi Name";
   const char* password = "Your WiFi Password";
   const char* serverUrl = "http://Server IP:8099/detect";
   ```
4. Upload code to ESP32-CAM

### 2. Server Configuration

1. Install Python dependencies:
   ```bash
   cd server
   pip install -r requirements.txt
   ```

2. Initialize database:
   ```bash
   python database.py
   ```

3. Start server:
   ```bash
   python app.py
   ```

Server will start at `http://0.0.0.0:8099`

## Usage

### Starting the System
1. Ensure ESP32-CAM and server are on the same WiFi network
2. Start Flask server
3. Power on ESP32-CAM
4. System will automatically start working

### Workflow
1. PIR sensor detects movement
2. ESP32-CAM captures image and sends to server
3. Server uses AI model to detect if there's a cat in the image
4. If cat is detected, turn on water dispenser; otherwise turn off
5. Repeat detection every 10 seconds until no cat is detected
6. Records are saved to database and static files

### Viewing Detection Records
Visit `http://Server IP:8099/log` to view recent detection records

## API Endpoints

### POST /detect
Receives image and returns detection result

**Request Format:**
```json
{
  "image": "base64 encoded image data"
}
```

**Response Format:**
```json
{
  "cat": true/false,
  "too_dark": true/false,
  "brightness": 0.0-255.0
}
```

### POST /toggle_brightness
Toggle brightness detection on/off

**Request Format:**
```json
{
  "enabled": true/false
}
```

**Response Format:**
```json
{
  "success": true/false,
  "enabled": true/false
}
```

### GET /brightness_status
Get current brightness detection status

**Response Format:**
```json
{
  "enabled": true/false
}
```

### GET /log
View detection history records

## Configuration

### Detection Parameters
- Detection interval: 10 seconds
- Image size: Maximum 640 pixels (auto-adjusted)
- Record retention: Latest 10 records
- No trigger timeout: Turn off water dispenser after 30 seconds

### Hardware Parameters
- PIR trigger: High level
- Water dispenser control: 500ms pulse
- LED indicator: Lights up during detection

### Brightness Detection
- Default brightness threshold: 30 (0-255 scale)
- Toggle switch available in web interface
- When disabled, all images are processed regardless of brightness

## Troubleshooting

### Common Issues

1. **WiFi Connection Failed**
   - Check if WiFi configuration is correct
   - Ensure good network signal

2. **Inaccurate Detection**
   - Adjust camera position and angle
   - Ensure adequate lighting
   - Check PIR sensor sensitivity

3. **Water Dispenser Not Working**
   - Check relay wiring
   - Confirm water dispenser power
   - Check GPIO configuration

4. **Server Connection Failed**
   - Check server IP address
   - Confirm port 8099 is accessible
   - Check firewall settings

5. **Images Too Dark**
   - Adjust camera position for better lighting
   - Use the toggle switch to disable brightness detection if needed
   - Check if camera lens is clean

### Debug Information
ESP32-CAM outputs detailed debug information through serial port at 115200 baud rate.

## Project Structure

```
cat_water_feed/
├── cam/
│   └── sketch_sep21a/
│       └── sketch_sep21a.ino    # ESP32-CAM main program
├── server/
│   ├── app.py                   # Flask server main program
│   ├── detection.py             # AI detection module
│   ├── database.py              # Database operations
│   ├── requirements.txt         # Python dependencies
│   ├── static/                  # Image storage directory
│   └── test/                    # Test files
├── detect.db                    # SQLite database
└── readme.md                    # Project documentation
```

## Technology Stack

- **Hardware**: ESP32-CAM, PIR sensor, relay module
- **Embedded**: Arduino C++, ESP32 framework
- **Backend**: Python, Flask, SQLite
- **AI**: PaddlePaddle, PaddleClas
- **Image Processing**: OpenCV, NumPy

## License

This project is licensed under the MIT License.

## Contributing

Issues and Pull Requests are welcome to improve this project!

## Changelog

- v1.0.0: Initial version with basic cat detection and water dispenser control
- v1.1.0: Added dark image detection and brightness toggle functionality
  - Support for PIR trigger detection
  - Integrated PaddleClas AI model
  - Automatic record management and cleanup
  - Web interface for viewing history records
  - Dark image detection with configurable threshold
  - Web-based toggle switch for brightness detection control
  - Enhanced API endpoints for brightness management
