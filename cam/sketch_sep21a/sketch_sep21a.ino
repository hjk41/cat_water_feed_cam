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

#define PIR_GPIO   13
int faucet_control_pos = 14;
int faucet_control_neg = 15;
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
  pinMode(PIR_GPIO, INPUT);
  pinMode(faucet_control_pos, OUTPUT);
  pinMode(faucet_control_neg, OUTPUT);
  digitalWrite(faucet_control_pos, LOW);
  digitalWrite(faucet_control_neg, LOW);
  SetFaucet(TURN_OFF);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  // 摄像头初始化
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

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed 0x%x", err);
    ESP.restart();
  }
}

// 拍照 → base64 → POST JSON → 解析结果
bool detectCat() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return false;
  }
  String b64 = base64::encode(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  String body = "{\"image\":\"" + b64 + "\"}";
  int code = http.POST(body);
  bool cat = false;
  if (code == 200) {
    String payload = http.getString();
    Serial.println(payload);
    cat = (payload.indexOf("\"cat\":true") >= 0);
  } else {
    Serial.printf("Server err %d\n", code);
  }
  http.end();
  return cat;
}

void loop() {
  static unsigned long lastPIRTriggerTime = 0;

  // Check PIR sensor
  if (digitalRead(PIR_GPIO) == HIGH) {
    lastPIRTriggerTime = millis();
    Serial.println("PIR triggered → start detection loop");
    while (true) {
      bool hasCat = detectCat();
      if (hasCat) {
        // Turn on water fountain
        SetFaucet(TURN_ON);
        Serial.println("Cat found → keep ON");
      } else {
        // Turn off water fountain
        SetFaucet(TURN_OFF);
        Serial.println("No cat → OFF & exit loop");
        break;
      }
      delay(20000);  // 20 seconds delay before next detection
    }
  }
  else {
    // Turn off faucet if no PIR trigger for 30 seconds
    if (millis() - lastPIRTriggerTime > 30000) {
      SetFaucet(TURN_OFF);
      Serial.println("No PIR trigger for 30s → faucet OFF");
    }
  }
  delay(500);  // Small delay to avoid busy looping
}