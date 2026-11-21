#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>

#define PINO_SERVO 18
#define PINO_LED_VERDE 19 
#define PINO_LED_VERMELHO 21

Servo tranca;

// ==========================================
// CONFIGURAÇÕES DE TEMPO E "PENSAMENTO"
// ==========================================
bool portaAberta = false;
unsigned long tempoAbertura = 0;
const unsigned long TEMPO_PERMANENCIA = 5000; // Tempo de porta aberta: 5 segundos

// NOVIDADE: A placa agora "pensa" antes de abrir
int contadorReconhecimento = 0;
const int FOTOS_NECESSARIAS = 3; // Exige 3 acertos seguidos para abrir a porta

typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosRecebidos;

// Função que recebe o sinal do Python
void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
    memcpy(&dadosRecebidos, incomingData, sizeof(dadosRecebidos));
    
    // Só processa se a porta estiver trancada
    if (!portaAberta) {
        if (dadosRecebidos.reconhecido == true) {
            
            // Em vez de abrir na hora, adiciona na contagem!
            contadorReconhecimento++;
            Serial.print("Analisando rosto... Confirmacao: ");
            Serial.print(contadorReconhecimento);
            Serial.print(" de ");
            Serial.println(FOTOS_NECESSARIAS);

            // Se atingiu as 3 confirmações seguidas, destrava!
            if (contadorReconhecimento >= FOTOS_NECESSARIAS) {
                tranca.write(90); 
                digitalWrite(PINO_LED_VERDE, HIGH);
                digitalWrite(PINO_LED_VERMELHO, LOW);
                
                portaAberta = true;
                tempoAbertura = millis();
                contadorReconhecimento = 0; // Zera para a próxima pessoa
                Serial.println("ACESSO CONFIRMADO! Porta destrancada por 5 segundos.");
            }
            
        } else {
            // Se der acesso negado, quebra a sequência. A pessoa tem que ficar parada.
            contadorReconhecimento = 0;
            
            tranca.write(0); // Garante que o motor fique no 0
            digitalWrite(PINO_LED_VERDE, LOW);
            digitalWrite(PINO_LED_VERMELHO, HIGH);
        }
    }
}

void setup() {
    Serial.begin(115200);
    
    tranca.attach(PINO_SERVO);
    pinMode(PINO_LED_VERDE, OUTPUT);
    pinMode(PINO_LED_VERMELHO, OUTPUT);
    
    // Posição inicial segura (Trancada)
    tranca.write(0);
    digitalWrite(PINO_LED_VERDE, LOW);
    digitalWrite(PINO_LED_VERMELHO, LOW);

    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) {
        Serial.println("Erro ESP-NOW");
        return;
    }
    
    esp_now_register_recv_cb(esp_now_recv_cb_t(OnDataRecv));
}

void loop() {
    // Relógio que tranca a porta sozinha após 5 segundos
    if (portaAberta) {
        if (millis() - tempoAbertura >= TEMPO_PERMANENCIA) {
            tranca.write(0);
            digitalWrite(PINO_LED_VERDE, LOW);
            digitalWrite(PINO_LED_VERMELHO, LOW);
            
            portaAberta = false;
            Serial.println("Tempo esgotado. Porta trancada novamente.");
        }
    }
    delay(10); // Respiro pro microcontrolador
}