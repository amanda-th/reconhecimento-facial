#include <esp_now.h>
#include <WiFi.h>
#include <ESP32Servo.h>

// Definição dos pinos físicos
#define PINO_SERVO 18
#define LED_VERDE 19
#define LED_VERMELHO 21

Servo trancaServo;

// A estrutura DEVE ser exatamente igual à da ESP32 transmissora
typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosRecebidos;

// =========================================================================
// CALLBACK: Função chamada automaticamente sempre que um pacote chegar
// =========================================================================
void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
    // Copia os bytes recebidos para a nossa variável
    memcpy(&dadosRecebidos, incomingData, sizeof(dadosRecebidos));

    if (dadosRecebidos.reconhecido) {
        Serial.println("Sinal recebido: ACESSO LIBERADO. Abrindo tranca...");
        digitalWrite(LED_VERDE, HIGH);
        digitalWrite(LED_VERMELHO, LOW);
        trancaServo.write(90); // Gira o servo para 90 graus (Abre)
        
    } else {
        Serial.println("Sinal recebido: ACESSO NEGADO. Mantendo tranca fechada.");
        digitalWrite(LED_VERDE, LOW);
        digitalWrite(LED_VERMELHO, HIGH);
        trancaServo.write(0); // Volta o servo para 0 graus (Fecha)
    }
}

// =========================================================================
void setup() {
    Serial.begin(115200);
    
    // 1. Configura os Pinos
    pinMode(LED_VERDE, OUTPUT);
    pinMode(LED_VERMELHO, OUTPUT);
    
    // Estado inicial: Tranca fechada (Vermelho aceso, Servo em 0)
    digitalWrite(LED_VERDE, LOW);
    digitalWrite(LED_VERMELHO, HIGH);
    
    // Configura o Servo de acordo com as exigências da ESP32
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    trancaServo.setPeriodHertz(50); // Frequência padrão de servos
    trancaServo.attach(PINO_SERVO, 500, 2400); // Pinos e larguras de pulso
    trancaServo.write(0);

    // 2. Configura Wi-Fi em modo Station
    WiFi.mode(WIFI_STA);

    // =========================================================================
    // O MOMENTO MÁGICO: Imprime o MAC Address que você precisa!
    // =========================================================================
    Serial.println("\n--- INFORMAÇÕES DA PLACA ---");
    Serial.print("Endereço MAC desta ESP32: ");
    Serial.println(WiFi.macAddress());
    Serial.println("----------------------------\n");

    // 3. Inicializa ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Erro ao inicializar ESP-NOW");
        return;
    }

    // Registra a função de Callback para quando receber dados
    esp_now_register_recv_cb(OnDataRecv);
}

void loop() {
    // Como a recepção de dados via rádio é feita por hardware/interrupção (Callback),
    // o loop principal pode ficar completamente vazio! O microcontrolador fica livre.
}