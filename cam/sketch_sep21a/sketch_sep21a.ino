/*
 *  ESP32-CAM 红外触发 → 每 10s 拍照 → POST 到 Flask /detect
 *  检测到猫：SetFaucet(TURN_ON)（开饮水机）→ 继续循环
 *  未检测到猫：SetFaucet(TURN_OFF)（关饮水机）→ 退出循环
 *  硬件：
 *    PIR 接 GPIO13（上拉），高电平触发
 *    饮水机继电器接 GPIO14,15（正负控制）
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <base64.h>
#include <ArduinoOTA.h>

#include "wifi_config.h"

#define PIR_GPIO  15
#define LED_GPIO   4  // ESP32-CAM onboard LED
int faucet_control_pos = 12;
int faucet_control_neg = 13;
int PIR_ON_IND = 14;
// ===========================================================

// AI-Thinker 引脚映射
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35 
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

int faucet_delay_ms = 500;

enum FaucetAction {
  TURN_ON,
  TURN_OFF
};

enum DetectionResult {
  CAT_DETECTED,    // Cat was detected by server
  IMAGE_TOO_DARK,  // Image is too dark to analyze
  NO_CAT,          // No cat detected
  ERROR            // Network/camera error
};

// LED control with brightness setting
void setLEDBrightness(int brightness) {
  if (brightness > 0) {
    analogWrite(LED_GPIO, brightness);
  } else {
    // Ensure LED is completely off
    digitalWrite(LED_GPIO, LOW);
    analogWrite(LED_GPIO, 0);  // Also set PWM to 0 to ensure it's off
  }
}



// Function to manually adjust white balance if needed
void adjustWhiteBalance() {
  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    // Set white balance to auto
    s->set_whitebal(s, 1);  // Auto white balance
    s->set_awb_gain(s, 1);  // Enable AWB gain
    s->set_wb_mode(s, 0);   // 0=Auto, 1=Sunny, 2=Cloudy, 3=Office, 4=Home
    
    // Allow time for white balance to stabilize (especially important for first photo)
    delay(1000);  // Increased delay to allow white balance to fully adjust
    
    Serial.println("White balance adjusted");
  }
}

// Function to set camera flip settings - must be called after white balance
void setCameraFlip() {
  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    // Set both horizontal and vertical flip to achieve 180-degree rotation
    s->set_hmirror(s, 1);  // Horizontal mirror (flip horizontally)
    s->set_vflip(s, 1);    // Vertical flip (flip vertically)
    delay(100);  // Small delay to ensure flip settings are applied
    Serial.println("Camera flip settings applied (180-degree rotation)");
  } else {
    Serial.println("Warning: Could not get camera sensor for flip settings");
  }
}

void SetFaucet(FaucetAction action) {
  if (action == TURN_ON) {
    digitalWrite(faucet_control_pos, HIGH);
    digitalWrite(faucet_control_neg, LOW);
  } else {
    digitalWrite(faucet_control_pos, LOW);
    digitalWrite(faucet_control_neg, HIGH);
  }
  delay(faucet_delay_ms);
  digitalWrite(faucet_control_pos, LOW);
  digitalWrite(faucet_control_neg, LOW);
}

// Non-blocking delay that allows OTA updates during wait
// Also checks WiFi connection and reconnects if needed
void delayWithOTA(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    // Check WiFi connection and reconnect if needed
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi disconnected, attempting to reconnect...");
      WiFi.disconnect();
      WiFi.begin(ssid, password);
      
      int reconnectAttempts = 0;
      while (WiFi.status() != WL_CONNECTED && reconnectAttempts < 2) {
        delay(500);
        Serial.print(".");
        reconnectAttempts++;
      }
      
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi reconnected");
        Serial.print("IP address: ");
        Serial.println(WiFi.localIP());
        
        // Reinitialize OTA after reconnection
        ArduinoOTA.setHostname("esp32-cam-cat-feeder");
        ArduinoOTA.begin();
        Serial.println("OTA reinitialized");
      } else {
        Serial.println("\nWiFi reconnection failed");
      }
    }
    
    ArduinoOTA.handle();
    delay(10);
  }
}


camera_config_t config;

void setup() {
  Serial.begin(115200);
  delay(1000);  // Give serial time to initialize
  Serial.println("Starting setup...");
  
  pinMode(PIR_GPIO, INPUT_PULLDOWN);  // Enable internal pull-down resistor
  pinMode(LED_GPIO, OUTPUT);
  pinMode(faucet_control_pos, OUTPUT);
  pinMode(faucet_control_neg, OUTPUT);
  pinMode(PIR_ON_IND, OUTPUT);
  digitalWrite(PIR_ON_IND, LOW);
  digitalWrite(faucet_control_pos, LOW);
  digitalWrite(faucet_control_neg, LOW);
  setLEDBrightness(1);
  SetFaucet(TURN_OFF);
  
  Serial.println("GPIO pins configured");

  Serial.println("Starting WiFi connection...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) {
    delay(1000);
    Serial.print(".");
    wifiAttempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    
    // Initialize OTA
    ArduinoOTA.setHostname("esp32-cam-cat-feeder");
    // ArduinoOTA.setPassword("admin");  // Optional: uncomment to set password
    
    ArduinoOTA.begin();
    Serial.println("OTA ready");
  } else {
    Serial.println("\nWiFi connection failed - continuing anyway");
  }
  
  Serial.println("WiFi setup complete - LED set to off");

  // 摄像头初始化
  Serial.println("Initializing camera...");
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;   // 320×240
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  Serial.println("Calling esp_camera_init...");
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error: 0x%x\n", err);
    Serial.println("Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();
  }
  Serial.println("Camera initialized successfully");
  
  // Configure camera settings to fix green tint
  Serial.println("Configuring camera settings...");
  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    // Set white balance to auto
    s->set_whitebal(s, 1);  // 1 = auto white balance
    s->set_awb_gain(s, 1);   // Enable AWB gain
    
    // Adjust brightness and contrast
    s->set_brightness(s, 0);     // Brightness: -2 to 2
    s->set_contrast(s, 0);       // Contrast: -2 to 2
    s->set_saturation(s, 0);     // Saturation: -2 to 2
    
    // Set color correction
    s->set_colorbar(s, 0);      // Disable color bar
    s->set_dcw(s, 1);           // Enable DCW (Downsize EN)
    
    // Set exposure and gain
    s->set_ae_level(s, 0);      // Auto exposure level: -2 to 2
    s->set_aec2(s, 1);          // Auto exposure control DSP: 0=off, 1=on
    s->set_gainceiling(s, (gainceiling_t)0);  // Gain ceiling: 0-6
    
    // Set special effects
    s->set_special_effect(s, 0); // Special effects: 0-6 (0=No Effect)
    
    Serial.println("Camera settings configured for better color balance");
  } else {
    Serial.println("Warning: Could not get camera sensor");
  }
  
  Serial.println("Setup complete - System ready with dim LED");
}

// 拍照 → base64 → POST JSON → 解析结果（包含亮度检测）
// 返回检测结果：CAT_DETECTED, IMAGE_TOO_DARK, NO_CAT, ERROR
DetectionResult detectCat() {
  Serial.println("Starting detection");
  
  // Check WiFi connection before proceeding
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected - treating as error");
    return ERROR;  // 网络断开时返回错误
  }
  
  // Adjust white balance first
  adjustWhiteBalance();
  // Then apply flip settings (must be after white balance to ensure they persist)
  setCameraFlip();
  // Additional delay to ensure all settings are applied before capture
  delay(200);
  
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed - treating as error");
    return ERROR;  // 摄像头失败时返回错误
  }
  
  Serial.printf("Captured image: %dx%d, %d bytes\n", fb->width, fb->height, fb->len);
  
  String b64 = base64::encode(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  HTTPClient http;
  http.setTimeout(10000);  // 10 second timeout
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"image\":\"" + b64 + "\"}";
  
  Serial.println("Sending request to server...");
  int code = http.POST(body);
  DetectionResult result = NO_CAT;
  if (code == 200) {
    String payload = http.getString();
    Serial.println("Server response: " + payload);
    
    // Parse server response for cat detection and brightness
    if (payload.indexOf("\"cat\":true") >= 0) {
      result = CAT_DETECTED;
    } else if (payload.indexOf("\"too_dark\":true") >= 0) {
      result = IMAGE_TOO_DARK;
    } else {
      result = NO_CAT;
    }
  } else {
    Serial.printf("Server error %d - treating as error\n", code);
    result = ERROR;  // 服务器错误时返回错误
  }
  http.end();
  
  Serial.println("Detection complete");
  return result;
}

void loop() {  
  static unsigned long lastTriggerTime = 0;
  static unsigned long loopCount = 0;

  loopCount++;
  if (loopCount % 100 == 0) {  // Print status every 5 seconds
    Serial.printf("Loop running... PIR: %d, WiFi: %d\n", 
                  digitalRead(PIR_GPIO), WiFi.status());
  }

  // Check for PIR sensor trigger
  bool pirTriggered = (digitalRead(PIR_GPIO) == HIGH);
  Serial.printf("PIR: %d\n", pirTriggered);

  if (pirTriggered) {
    digitalWrite(PIR_ON_IND, true);
    lastTriggerTime = millis();
    Serial.println("PIR triggered → starting detection");
    
    // Perform single detection
    DetectionResult result = detectCat();
    
    if (result == CAT_DETECTED) {
      Serial.println("Cat detected → entering detection loop");
      
      // Detection loop - runs every 10 seconds until no cat detected
      int detectionCount = 0;
      while (true) {
        detectionCount++;
        Serial.printf("Detection attempt #%d\n", detectionCount);
        
        DetectionResult loopResult = detectCat();
        if (loopResult == CAT_DETECTED) {
          // Turn on water fountain
          SetFaucet(TURN_ON);
          Serial.println("Cat found → keep ON");
        } else {
          // Turn off water fountain
          SetFaucet(TURN_OFF);
          Serial.println("No cat → exit detection loop");
          break;  // Exit detection loop when no cat detected
        }
        
        Serial.println("Waiting 10 seconds before next detection...");
        delayWithOTA(10000);  // Wait 10 seconds before next detection
      }
      Serial.println("Exited detection loop");
    } else if (result == IMAGE_TOO_DARK || result == ERROR) {
      Serial.println("Image too dark or server error → turning on faucet for 30 seconds");
      SetFaucet(TURN_ON);
      delayWithOTA(30000);
      SetFaucet(TURN_OFF);
    } else {  // NO_CAT
      Serial.println("No cat detected → faucet OFF");
      SetFaucet(TURN_OFF);
      delayWithOTA(500);
    }
  }
  else {
    digitalWrite(PIR_ON_IND, false);
    // Turn off faucet if no trigger for 30 seconds
    if (millis() - lastTriggerTime > 30000) {
      SetFaucet(TURN_OFF);
      lastTriggerTime = millis();
      Serial.println("No PIR trigger for 30s → faucet OFF");
    }
  }
  
  delayWithOTA(1000);  // Small delay to avoid busy looping
}