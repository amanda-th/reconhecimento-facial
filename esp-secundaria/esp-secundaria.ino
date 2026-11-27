#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>

#define PINO_SERVO 18
#define PINO_LED_VERDE 19 
#define PINO_LED_VERMELHO 21

Servo tranca;

// =========================================================================
// MÁQUINA DE ESTADOS E TEMPORIZADORES
// =========================================================================
enum EstadoPorta {
    TRANCADA,
    MOVENDO_PARA_ABRIR,
    ABERTA,
    MOVENDO_PARA_FECHAR
};

EstadoPorta estadoAtual = TRANCADA;

unsigned long tempoAbertura = 0;
unsigned long tempoInicioMovimento = 0;
unsigned long tempoUltimoFechamento = 0;

const unsigned long TEMPO_PERMANENCIA = 5000;
const unsigned long TEMPO_MOVIMENTO_SERVO = 500; 
const unsigned long TEMPO_COOLDOWN = 1500;

// Flags de comunicação entre o Callback (Wi-Fi) e o Loop (Física)
volatile bool solicitarAbertura = false;
volatile bool solicitarFechamento = false;

int contadorReconhecimento = 0;
const int FOTOS_NECESSARIAS = 3; 

typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosRecebidos;

// =========================================================================
// CALLBACK DO ESP-NOW (Rápido, sem delays)
// =========================================================================
void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
    memcpy(&dadosRecebidos, incomingData, sizeof(dadosRecebidos));
    
    if (estadoAtual == TRANCADA) {
        if (millis() - tempoUltimoFechamento > TEMPO_COOLDOWN) {
            
            if (dadosRecebidos.reconhecido == true) {
                contadorReconhecimento++;
                if (contadorReconhecimento >= FOTOS_NECESSARIAS) {
                    solicitarAbertura = true; // Levanta a bandeira, não roda motor aqui!
                    contadorReconhecimento = 0; 
                }
            } else {
                contadorReconhecimento = 0;
                solicitarFechamento = true; 
            }
        }
    }
}

// =========================================================================
// SETUP
// =========================================================================
void setup() {
    Serial.begin(115200);
    
    pinMode(PINO_LED_VERDE, OUTPUT);
    pinMode(PINO_LED_VERMELHO, OUTPUT);
    
    tranca.attach(PINO_SERVO);
    tranca.write(0);
    delay(500); // Apenas no boot é aceitável
    tranca.detach();

    pinMode(PINO_SERVO, OUTPUT); 
    digitalWrite(PINO_SERVO, LOW);
    
    digitalWrite(PINO_LED_VERDE, LOW);
    digitalWrite(PINO_LED_VERMELHO, HIGH); 
    
    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Erro ESP-NOW");
        return;
    }
    
    esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
}

// =========================================================================
// LOOP PRINCIPAL (Máquina de Estados Não-Bloqueante)
// =========================================================================
void loop() {
    
    switch (estadoAtual) {
        
        case TRANCADA:
            if (solicitarAbertura) {
                solicitarAbertura = false;
                solicitarFechamento = false;
                
                tranca.attach(PINO_SERVO);
                tranca.write(90);
                digitalWrite(PINO_LED_VERDE, HIGH);
                digitalWrite(PINO_LED_VERMELHO, LOW);
                
                estadoAtual = MOVENDO_PARA_ABRIR;
                tempoInicioMovimento = millis();
                Serial.println("ACESSO LIBERADO: Iniciando abertura...");
            }
            else if (solicitarFechamento) {
                solicitarFechamento = false;
                // Motor já está em 0, só garante os LEDs
                digitalWrite(PINO_LED_VERDE, LOW);
                digitalWrite(PINO_LED_VERMELHO, HIGH);
            }
            break;
            
        case MOVENDO_PARA_ABRIR:
            if (millis() - tempoInicioMovimento >= TEMPO_MOVIMENTO_SERVO) {
                tranca.detach();
                
                // Força o pino para zero volts (Mata o ruído de RF da antena)
                pinMode(PINO_SERVO, OUTPUT); 
                digitalWrite(PINO_SERVO, LOW); 
                
                estadoAtual = ABERTA;
                tempoAbertura = millis();
                Serial.println("Porta fisicamente aberta.");
            }
            break;
            
        case ABERTA:
            if (millis() - tempoAbertura >= TEMPO_PERMANENCIA) {
                tranca.attach(PINO_SERVO);
                tranca.write(0);
                digitalWrite(PINO_LED_VERDE, LOW);
                digitalWrite(PINO_LED_VERMELHO, HIGH);
                
                estadoAtual = MOVENDO_PARA_FECHAR;
                tempoInicioMovimento = millis();
                Serial.println("Tempo esgotado: Iniciando fechamento...");
            }
            break;
            
        case MOVENDO_PARA_FECHAR:
            if (millis() - tempoInicioMovimento >= TEMPO_MOVIMENTO_SERVO) {
                tranca.detach();
                
                // Força o pino para zero volts (Mata o ruído de RF da antena)
                pinMode(PINO_SERVO, OUTPUT); 
                digitalWrite(PINO_SERVO, LOW); 
                
                estadoAtual = TRANCADA;
                tempoUltimoFechamento = millis();
                solicitarAbertura = false; 
                Serial.println("Porta fisicamente trancada. Cooldown ativado.");
            }
            break;
    }
    
    // O microcontrolador respira livremente a cada ciclo
    delay(10); 
}