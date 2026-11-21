#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>

#define PINO_SERVO 18
#define PINO_LED_VERDE 19 
#define PINO_LED_VERMELHO 21

Servo tranca;

bool portaAberta = false;
unsigned long tempoAbertura = 0;
const unsigned long TEMPO_PERMANENCIA = 5000;

// NOVIDADE: Variáveis do Cooldown (Período de Refração)
unsigned long tempoUltimoFechamento = 0;
const unsigned long TEMPO_COOLDOWN = 1500; // Fica "surdo" por 1.5s após fechar

int contadorReconhecimento = 0;
const int FOTOS_NECESSARIAS = 3; 
bool servoJaEstaNoZero = false; 

typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosRecebidos;

void moverServo(int angulo) {
    tranca.attach(PINO_SERVO); 
    tranca.write(angulo);      
    delay(500);                
    tranca.detach();           
}

void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
    memcpy(&dadosRecebidos, incomingData, sizeof(dadosRecebidos));
    
    // Regra 1: Só avalia novos acessos se a porta já estiver fechada
    if (!portaAberta) {
        
        // Regra 2: Só escuta a câmera se o "Cooldown" de fechamento já passou!
        if (millis() - tempoUltimoFechamento > TEMPO_COOLDOWN) {
            
            if (dadosRecebidos.reconhecido == true) {
                contadorReconhecimento++;
                
                if (contadorReconhecimento >= FOTOS_NECESSARIAS) {
                    moverServo(90); 
                    digitalWrite(PINO_LED_VERDE, HIGH);
                    digitalWrite(PINO_LED_VERMELHO, LOW);
                    
                    portaAberta = true;
                    servoJaEstaNoZero = false; 
                    tempoAbertura = millis();
                    contadorReconhecimento = 0; 
                    Serial.println("ACESSO LIBERADO!");
                }
            } else {
                contadorReconhecimento = 0;
                
                if (!servoJaEstaNoZero) {
                    moverServo(0); 
                    digitalWrite(PINO_LED_VERDE, LOW);
                    digitalWrite(PINO_LED_VERMELHO, HIGH);
                    servoJaEstaNoZero = true; 
                    Serial.println("Porta trancada e aguardando rosto...");
                }
            }
        }
    }
}

void setup() {
    Serial.begin(115200);
    
    pinMode(PINO_LED_VERDE, OUTPUT);
    pinMode(PINO_LED_VERMELHO, OUTPUT);
    
    moverServo(0);
    digitalWrite(PINO_LED_VERDE, LOW);
    digitalWrite(PINO_LED_VERMELHO, HIGH); 
    servoJaEstaNoZero = true;

    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Erro ESP-NOW");
        return;
    }
    
    esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
}

void loop() {
    if (portaAberta) {
        if (millis() - tempoAbertura >= TEMPO_PERMANENCIA) {
            moverServo(0);
            digitalWrite(PINO_LED_VERDE, LOW);
            digitalWrite(PINO_LED_VERMELHO, HIGH);
            
            portaAberta = false;
            servoJaEstaNoZero = true; 
            
            // Inicia o cronômetro do Cooldown no exato momento que a porta fecha
            tempoUltimoFechamento = millis(); 
            contadorReconhecimento = 0; // Zera qualquer contagem fantasma
            
            Serial.println("Tempo esgotado. Porta trancada. Cooldown ativado.");
        }
    }
    delay(10); 
}