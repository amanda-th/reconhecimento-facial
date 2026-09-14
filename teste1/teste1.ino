#include <Arduino.h>
#include <math.h>
#include <WiFi.h>
#include <esp_now.h>

// Substitua pelo endereço MAC da sua segunda ESP32 (A que tem o Servo/LED)
uint8_t macESP2[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}; 

#define WIDTH 64
#define HEIGHT 64
#define FRAME_SIZE (WIDTH * HEIGHT)

uint8_t inputImage[HEIGHT][WIDTH];
uint8_t outputImage[HEIGHT][WIDTH];

// O "Banco de Dados" (O rosto ideal)
// TODO: Mais tarde precisaremos capturar seu rosto real e colar os valores aqui
uint8_t rostoIdeal[HEIGHT][WIDTH] = {0}; 

// Estrutura do pacote de dados que será enviado via ESP-NOW
typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosEnvio;
esp_now_peer_info_t peerInfo;

const int Gx[3][3] = {{-1, 0, 1}, {-2, 0, 2}, {-1, 0, 1}};
const int Gy[3][3] = {{ 1, 2, 1}, { 0, 0, 0}, {-1,-2,-1}};

TaskHandle_t TaskProcess_Handle;

// =========================================================================
void aplicarSobel() {
    for (int y = 1; y < HEIGHT - 1; y++) {
        for (int x = 1; x < WIDTH - 1; x++) {
            int somaX = 0, somaY = 0;
            for (int i = -1; i <= 1; i++) {
                for (int j = -1; j <= 1; j++) {
                    int pixel = inputImage[y + i][x + j];
                    somaX += pixel * Gx[i + 1][j + 1];
                    somaY += pixel * Gy[i + 1][j + 1];
                }
            }
            int magnitude = sqrt((somaX * somaX) + (somaY * somaY));
            if (magnitude > 255) magnitude = 255;
            outputImage[y][x] = (uint8_t)magnitude;
        }
    }
}

// =========================================================================
// ALGORITMO DE CLASSIFICAÇÃO (SAD)
// =========================================================================
bool classificarRosto() {
    long diferencaTotal = 0;
    for (int y = 1; y < HEIGHT - 1; y++) {
        for (int x = 1; x < WIDTH - 1; x++) {
            diferencaTotal += abs(outputImage[y][x] - rostoIdeal[y][x]);
        }
    }
    
    // Threshold (limiar). Quanto MENOR, mais rigoroso (difícil de aceitar).
    // Esse valor precisará ser calibrado testando na prática.
    long threshold = 150000; 
    
    return (diferencaTotal < threshold);
}

// =========================================================================
void receiveSerialTask(void *pvParameters) {
    for (;;) {
        if (Serial.available() > 0) {
            if (Serial.read() == 'S') {
                size_t lidos = Serial.readBytes((uint8_t*)inputImage, FRAME_SIZE);
                if (lidos == FRAME_SIZE) {
                    xTaskNotifyGive(TaskProcess_Handle);
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(5)); 
    }
}

// =========================================================================
void processImageTask(void *pvParameters) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // 1. Extração de Características
        aplicarSobel();

        // 2. Classificação
        bool ehOAluno = classificarRosto();

        // 3. Comunicação de Tempo Real (ESP-NOW)
        dadosEnvio.reconhecido = ehOAluno;
        esp_now_send(macESP2, (uint8_t *) &dadosEnvio, sizeof(dadosEnvio));

        // 4. Libera o PC para enviar a próxima imagem
        Serial.println("OK");
    }
}

// =========================================================================
void setup() {
    Serial.begin(115200);
    Serial.setTimeout(500); 

    // Inicialização do Wi-Fi em modo Station (necessário para ESP-NOW)
    WiFi.mode(WIFI_STA);

    // Inicializa o protocolo ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Erro ao inicializar ESP-NOW");
        return;
    }

    // Registra a segunda ESP32 (Peer) para podermos enviar dados para ela
    memcpy(peerInfo.peer_addr, macESP2, 6);
    peerInfo.channel = 0;  
    peerInfo.encrypt = false;
    
    if (esp_now_add_peer(&peerInfo) != ESP_OK){
        Serial.println("Falha ao adicionar peer");
        return;
    }

    xTaskCreatePinnedToCore(receiveSerialTask, "RxTask", 4096, NULL, 1, NULL, 0);
    xTaskCreatePinnedToCore(processImageTask, "ProcTask", 8192, NULL, 2, &TaskProcess_Handle, 1);
}

void loop() {
    vTaskDelete(NULL); 
}