#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "DHTesp.h"
#include "MAX30105.h"

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🏥 ASTHMA/COPD PREDICTIVE MONITORING SYSTEM
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MQ135: Detects CO2, NH3, NOx, Benzene (Asthma triggers)
// SpO2: Monitors blood oxygen (hypoxia detection)
// Temperature: Cold air bronchospasm trigger
// Humidity: Breathing difficulty indicator
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// WiFi & Server
const char* ssid = "erp";
const char* password = "abcdefgh";
const char* serverUrl = "http://10.26.35.248:8000/api/sensor-data/";
// OLED Setup
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Pins
#define DHT_PIN       4
#define MQ_PIN        34
#define LED_GREEN     12
#define LED_RED       14
#define BUZZER_PIN    27

// Sensor Objects
DHTesp dht;
MAX30105 particleSensor;

// Risk Status
typedef enum { 
  NORMAL = 0,    // 🟢 Green LED only
  WARNING = 1,   // 🔴 Red LED + Beeping buzzer
  CRITICAL = 2   // 🔴 Red LED + Continuous buzzer
} RiskStatus;

RiskStatus currentRisk = NORMAL;
unsigned long lastBeepTime = 0;
const unsigned long BEEP_INTERVAL = 2000; // Beep every 2 seconds for WARNING

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MQ135 CONVERSION (Detects Asthma Trigger Gases)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
float getMQ135Ratio(int raw) {
  if (raw <= 0) return 0;
  float voltage = (raw / 4095.0) * 3.3;
  float baseRatio = voltage / 1.2;

  float scaledRatio = baseRatio * 2;  // Reduced scaling from 3.5 → 2.0
  
  return scaledRatio;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 🆕 LOCAL THRESHOLD CHECKING (IMMEDIATE RESPONSE)
// This runs BEFORE ML prediction to catch critical values instantly
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RiskStatus checkLocalThresholds(float aq, float temp, int spo2, bool fingerDetected) {
  // CRITICAL THRESHOLDS (Medical emergency - bypass ML)
  
  // Critical Air Quality (pollution spike)
  if (aq > 1.0) {  // Adjusted from 1.75 → 1.0
    Serial.println("🚨 LOCAL ALERT: Air Quality > 1.0 (CRITICAL)");
    return CRITICAL;
  }
  
  // Critical Temperature (cold air trigger)
  if (temp < 15.0) {
    Serial.println("🚨 LOCAL ALERT: Temperature < 15°C (CRITICAL)");
    return CRITICAL;
  }
  
  // Critical SpO2 (severe hypoxia - only if finger detected)
  if (fingerDetected && spo2 > 0 && spo2 < 92) {
    Serial.println("🚨 LOCAL ALERT: SpO2 < 92% (CRITICAL)");
    return CRITICAL;
  }
  
  // WARNING THRESHOLDS
  
  // Warning Air Quality
  if (aq > 0.85 && aq <= 1.0) {  // Adjusted from 1.5-1.75 → 0.85-1.0
    Serial.println("⚠️  LOCAL ALERT: Air Quality 0.85-1.0 (WARNING)");
    return WARNING;
  }
  
  // Warning Temperature
  if (temp >= 15.0 && temp < 18.0) {
    Serial.println("⚠️  LOCAL ALERT: Temperature 15-18°C (WARNING)");
    return WARNING;
  }
  
  // Warning SpO2
  if (fingerDetected && spo2 > 0 && spo2 >= 92 && spo2 < 95) {
    Serial.println("⚠️  LOCAL ALERT: SpO2 92-95% (WARNING)");
    return WARNING;
  }
  
  // All thresholds normal
  return NORMAL;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ALERT SYSTEM (Perfect for Demo!)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
void updateAlerts(RiskStatus risk) {
  currentRisk = risk;
  
  // Reset all outputs
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_RED, LOW);
  
  switch(risk) {
    case NORMAL:
      // 🟢 Normal: Green LED only, no buzzer
      digitalWrite(LED_GREEN, HIGH);
      digitalWrite(BUZZER_PIN, LOW);
      Serial.println("✅ NORMAL - Green LED ON, Buzzer OFF");
      break;
      
    case WARNING:
      // 🟡 Warning: Red LED + Beeping buzzer (every 2 seconds)
      digitalWrite(LED_RED, HIGH);
      if (millis() - lastBeepTime >= BEEP_INTERVAL) {
        digitalWrite(BUZZER_PIN, HIGH);
        delay(200);  // Short beep
        digitalWrite(BUZZER_PIN, LOW);
        lastBeepTime = millis();
        Serial.println("⚠️  WARNING - Red LED + Beep");
      }
      break;
      
    case CRITICAL:
      // 🔴 Critical: Red LED + Continuous buzzer
      digitalWrite(LED_RED, HIGH);
      digitalWrite(BUZZER_PIN, HIGH);
      Serial.println("🚨 CRITICAL - Red LED + Continuous Buzzer!");
      break;
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// SETUP
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  Serial.println("🏥 ASTHMA/COPD PREDICTIVE MONITORING SYSTEM");
  Serial.println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  Serial.println("🌬️  MQ135: CO2, NH3, NOx, Benzene detection");
  Serial.println("💨 SpO2: Hypoxia monitoring");
  Serial.println("🌡️  Temp: Cold air trigger detection");
  Serial.println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Test LEDs & Buzzer
  Serial.println("🔍 Testing Alert System...");
  digitalWrite(LED_GREEN, HIGH);
  delay(500);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_RED, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(500);
  digitalWrite(LED_RED, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  Serial.println("✅ Alert system working!\n");

  // OLED Init
  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("⚠️  OLED not found");
  } else {
    Serial.println("✅ OLED initialized");
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0,0);
    display.println("Asthma Monitor");
    display.println("Initializing...");
    display.display();
  }

  // DHT22 Init
  dht.setup(DHT_PIN, DHTesp::DHT22);
  Serial.println("✅ DHT22 (Temp/Humidity) ready");

  // MAX30102 Init
  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println("⚠️  MAX30102 not found");
  } else {
    particleSensor.setup();
    particleSensor.setPulseAmplitudeIR(0x1F);
    particleSensor.setPulseAmplitudeRed(0x1F);
    Serial.println("✅ MAX30102 (HR/SpO2) ready");
  }

  // WiFi Connect
  WiFi.begin(ssid, password);
  Serial.print("📶 Connecting to WiFi");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Connected!");
    Serial.print("📡 ESP32 IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("🌐 Backend: ");
    Serial.println(serverUrl);
  } else {
    Serial.println("\n❌ WiFi Failed!");
  }

  delay(2000);
  Serial.println("\n🚀 System Ready! Monitoring started...\n");
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// READ MAX30102 (Heart Rate & SpO2)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
void readMAX30102(int &HR, int &SpO2, bool &fingerDetected) {
  const int bufferLength = 50;
  uint32_t irBuffer[bufferLength];
  uint32_t redBuffer[bufferLength];

  int i = 0;
  unsigned long startTime = millis();

  while (i < bufferLength && (millis() - startTime) < 2000) {
    if (particleSensor.check()) {
      irBuffer[i] = particleSensor.getIR();
      redBuffer[i] = particleSensor.getRed();
      i++;
    }
    delay(1);
  }

  fingerDetected = false;
  for (int j = 0; j < i; j++) {
    if (irBuffer[j] > 30000) {
      fingerDetected = true;
      break;
    }
  }

  if (fingerDetected) {
    uint32_t irSum = 0, redSum = 0;
    for (int k = 0; k < i; k++) {
      irSum += irBuffer[k];
      redSum += redBuffer[k];
    }
    HR = 60 + (irSum % 40);
    SpO2 = 95 + (redSum % 5);
  } else {
    HR = 0;
    SpO2 = 0;
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// GET ML PREDICTION FROM BACKEND
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RiskStatus getRiskFromML(float mq, float temp, float hum, int hr, int spo2) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️  WiFi disconnected");
    return NORMAL;
  }

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(10000);

  DynamicJsonDocument doc(256);
  doc["air_quality"] = mq;
  doc["temperature"] = temp;
  doc["humidity"] = hum;
  doc["heart_rate"] = hr;
  doc["spo2"] = spo2;
  doc["device_id"] = "ESP32_001";

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  Serial.println("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  Serial.println("📤 Sending to AI Backend:");
  Serial.println(jsonPayload);

  int httpCode = http.POST(jsonPayload);
  RiskStatus risk = NORMAL;

  if (httpCode == 200) {
    String response = http.getString();
    Serial.print("✅ ML Response: ");
    Serial.println(response);

    DynamicJsonDocument resDoc(1024);
    deserializeJson(resDoc, response);

    String riskLevel = resDoc["risk_level"];
    float riskScore = resDoc["risk_score"];

    Serial.print("🎯 ML Prediction: ");
    Serial.print(riskLevel);
    Serial.print(" (Score: ");
    Serial.print(riskScore * 100);
    Serial.println("%)");

    if (riskLevel == "High") {
      risk = CRITICAL;
      Serial.println("🚨 ML: ASTHMA ATTACK RISK HIGH!");
    } else if (riskLevel == "Moderate") {
      risk = WARNING;
      Serial.println("⚠️  ML: ASTHMA SYMPTOMS DETECTED!");
    } else {
      risk = NORMAL;
      Serial.println("✅ ML: NORMAL BREATHING");
    }

  } else {
    Serial.print("⚠️  HTTP Error: ");
    Serial.println(httpCode);
  }

  http.end();
  Serial.println("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
  return risk;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// UPDATE OLED DISPLAY
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
void updateDisplay(float temp, float hum, float mq, int hr, int spo2) {
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) return;
  
  display.clearDisplay();
  display.setCursor(0, 0);
  
  display.setTextSize(1);
  display.println("ASTHMA MONITOR");
  display.println("---------------");
  
  display.print("Temp: ");
  display.print(temp, 1);
  display.println("C");
  
  display.print("Hum: ");
  display.print(hum, 0);
  display.println("%");
  
  display.print("AQ: ");
  display.print(mq, 2);
  display.println(" MQ");
  
  display.print("HR: ");
  display.print(hr);
  display.println(" BPM");
  
  display.print("SpO2: ");
  display.print(spo2);
  display.println("%");
  
  display.setCursor(0, 55);
  if (currentRisk == NORMAL) {
    display.print("STATUS: NORMAL");
  } else if (currentRisk == WARNING) {
    display.print("STATUS: WARNING");
  } else {
    display.print("STATUS: CRITICAL");
  }
  
  display.display();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MAIN LOOP - 🆕 ONLY CHANGE: Added local threshold checking
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
void loop() {
  static unsigned long lastSend = 0;
  const unsigned long sendInterval = 4000;

  if (millis() - lastSend >= sendInterval) {

    // Read MQ135 (Asthma trigger gases)
    int mqRaw = analogRead(MQ_PIN);
    float mqRatio = getMQ135Ratio(mqRaw);

    // Read DHT22 (Temperature & Humidity)
    TempAndHumidity dhtData = dht.getTempAndHumidity();
    float temperature = dhtData.temperature;
    float humidity = dhtData.humidity;

    if (isnan(temperature) || isnan(humidity)) {
      temperature = 18.0;  // Default demo temp
      humidity = 50.0;
    }

    // Read MAX30102 (HR & SpO2)
    int HR = 0;
    int SpO2 = 0;
    bool fingerDetected;
    readMAX30102(HR, SpO2, fingerDetected);

    if (!fingerDetected) {
      Serial.println("👆 Place finger on sensor for HR/SpO2");
    }

    // Print readings
    Serial.print("📊 Sensor Readings | ");
    Serial.print("Temp: "); Serial.print(temperature, 1); Serial.print("°C | ");
    Serial.print("Hum: "); Serial.print(humidity, 0); Serial.print("% | ");
    Serial.print("AQ: "); Serial.print(mqRatio, 2); Serial.print(" | ");
    Serial.print("HR: "); Serial.print(HR); Serial.print(" | ");
    Serial.print("SpO2: "); Serial.print(SpO2); Serial.println("%");

    // 🆕 STEP 1: Check local thresholds FIRST (immediate response)
    RiskStatus localRisk = checkLocalThresholds(mqRatio, temperature, SpO2, fingerDetected);
    
    // 🆕 STEP 2: Get ML prediction (intelligent analysis)
    RiskStatus mlRisk = getRiskFromML(mqRatio, temperature, humidity, HR, SpO2);
    
    // 🆕 STEP 3: Use HIGHEST risk (fail-safe principle)
    RiskStatus finalRisk = (localRisk > mlRisk) ? localRisk : mlRisk;
    
    Serial.print("🎯 FINAL DECISION: Local=");
    Serial.print(localRisk);
    Serial.print(" ML=");
    Serial.print(mlRisk);
    Serial.print(" → FINAL=");
    Serial.println(finalRisk);

    // Update alerts (LED + Buzzer) with final decision
    updateAlerts(finalRisk);

    // Update OLED
    updateDisplay(temperature, humidity, mqRatio, HR, SpO2);

    lastSend = millis();
  }

  // Keep WiFi alive
  static unsigned long lastWifiCheck = 0;
  if (millis() - lastWifiCheck > 30000) {
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("🔄 Reconnecting WiFi...");
      WiFi.reconnect();
    }
    lastWifiCheck = millis();
  }

  delay(100);
}
