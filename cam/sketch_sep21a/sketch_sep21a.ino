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

#include "wifi_config.h"

#define PIR_GPIO  15
#define LED_GPIO   4  // ESP32-CAM onboard LED
int faucet_control_pos = 12;
int faucet_control_neg = 13;
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
    // Try different white balance settings
    s->set_whitebal(s, 1);  // Auto white balance
    delay(500);
    
    // If still green, try manual adjustment
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);   // 0=Auto, 1=Sunny, 2=Cloudy, 3=Office, 4=Home
    
    Serial.println("White balance adjusted");
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


camera_config_t config;

void setup() {
  Serial.begin(115200);
  delay(1000);  // Give serial time to initialize
  Serial.println("Starting setup...");
  
  pinMode(PIR_GPIO, INPUT_PULLDOWN);  // Enable internal pull-down resistor
  pinMode(LED_GPIO, OUTPUT);
  pinMode(faucet_control_pos, OUTPUT);
  pinMode(faucet_control_neg, OUTPUT);
  digitalWrite(faucet_control_pos, LOW);
  digitalWrite(faucet_control_neg, LOW);
  setLEDBrightness(0);  // Start with LED off
  SetFaucet(TURN_OFF);
  
  Serial.println("GPIO pins configured");

  Serial.println("Starting WiFi connection...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) {
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected");
  } else {
    Serial.println("\nWiFi connection failed - continuing anyway");
  }
  
  // Set LED to off initially
  setLEDBrightness(0);  // LED off
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
  config.frame_size = FRAMESIZE_VGA;   // 640×480
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
  
  // Apply camera flip settings for 180-degree rotation
  setCameraFlip();
  
  Serial.println("Setup complete - System ready with dim LED");
}

// Function to set camera flip settings
void setCameraFlip() {
  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    // Set both horizontal and vertical flip to achieve 180-degree rotation
    s->set_hmirror(s, 1);  // Horizontal mirror (flip horizontally)
    s->set_vflip(s, 1);    // Vertical flip (flip vertically)
    Serial.println("Camera flip settings applied (180-degree rotation)");
  } else {
    Serial.println("Warning: Could not get camera sensor for flip settings");
  }
}

// 拍照 → base64 → POST JSON → 解析结果
bool detectCat() {
  Serial.println("Starting detection");
  
  // Check WiFi connection before proceeding
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected - skipping detection");
    return false;
  }
  
  adjustWhiteBalance();
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return false;
  }
  
  Serial.printf("Captured image: %dx%d, %d bytes\n", fb->width, fb->height, fb->len);
  
  // Small delay to allow camera to adjust white balance
  delay(100);
  
  String b64 = base64::encode(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  HTTPClient http;
  http.setTimeout(10000);  // 10 second timeout
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"image\":\"" + b64 + "\"}";
  
  Serial.println("Sending request to server...");
  int code = http.POST(body);
  bool cat = false;
  if (code == 200) {
    String payload = http.getString();
    Serial.println("Server response: " + payload);
    cat = (payload.indexOf("\"cat\":true") >= 0);
  } else {
    Serial.printf("Server error %d\n", code);
  }
  http.end();
  
  Serial.println("Detection complete");
  return cat;
}

void loop() {
  static unsigned long lastTriggerTime = 0;
  static unsigned long loopCount = 0;

  loopCount++;
  if (loopCount % 100 == 0) {  // Print status every 5 seconds
    Serial.printf("Loop running... PIR: %d, WiFi: %d\n", digitalRead(PIR_GPIO), WiFi.status());
  }

  // Check for PIR sensor trigger
  bool pirTriggered = (digitalRead(PIR_GPIO) == HIGH);

  if (pirTriggered) {
    lastTriggerTime = millis();
    Serial.println("PIR triggered → entering detection loop");
    
    // Turn on LED at maximum brightness when entering detection loop
    setLEDBrightness(2);  // Maximum brightness (0-255)
    Serial.println("LED set to maximum brightness");
    
    // Detection loop - runs every 10 seconds until no cat detected
    int detectionCount = 0;
    while (true) {
      detectionCount++;
      Serial.printf("Detection attempt #%d\n", detectionCount);
      
      bool hasCat = detectCat();
      if (hasCat) {
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
      delay(10000);  // Wait 10 seconds before next detection
    }

    Serial.println("Exited detection loop");
  }
  else {
    // Turn off faucet if no trigger for 30 seconds
    if (millis() - lastTriggerTime > 30000) {
      SetFaucet(TURN_OFF);
      // Turn off LED when exiting detection loop
      setLEDBrightness(0);
      Serial.println("No PIR trigger for 30s → faucet OFF");
    }
  }
  
  delay(2000);  // Small delay to avoid busy looping
}