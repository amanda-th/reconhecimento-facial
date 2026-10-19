#include <Arduino.h>
#include <math.h>
#include <WiFi.h>
#include <esp_now.h>

// O arquivo de banco de dados precisará ser atualizado depois
#include "banco_rostos.h" 

// =========================================================================
// CONFIGURAÇÕES DO LBP DA TURMA
// =========================================================================
#define BLOCO 3
#define GRID_X 5
#define GRID_Y 5
#define TAMANHO_VETOR 6400 // 25 blocos * 256 bins

#define WIDTH 64
#define HEIGHT 64
#define FRAME_SIZE (WIDTH * HEIGHT)

// Matrizes globais para processamento na RAM
uint8_t inputImage[HEIGHT][WIDTH];
int integralImage[HEIGHT + 1][WIDTH + 1];
uint8_t resultadoLBP[HEIGHT][WIDTH];
int vetorLBPH[TAMANHO_VETOR];

// MAC Address da segunda ESP32 (Atuador)
uint8_t macESP2[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}; 

typedef struct struct_mensagem {
    bool reconhecido;
} struct_mensagem;

struct_mensagem dadosEnvio;
esp_now_peer_info_t peerInfo;
TaskHandle_t TaskProcess_Handle;

// =========================================================================
// FUNÇÕES MATEMÁTICAS DO LBP
// =========================================================================
int somaBloco(int x, int y, int tamanho) {
    int x1 = x; int y1 = y; int x2 = x + tamanho; int y2 = y + tamanho;
    return integralImage[y2][x2] - integralImage[y1][x2] - integralImage[y2][x1] + integralImage[y1][x1];
}

double calcularDistanciaEuclidiana(int *vetorNovaFoto, const double *vetorCentroide) {
    double soma_quadrados = 0.0;
    for (int i = 0; i < TAMANHO_VETOR; i++) {
        double diferenca = (double)vetorNovaFoto[i] - vetorCentroide[i];
        soma_quadrados += (diferenca * diferenca);
    }
    return sqrt(soma_quadrados);
}

// =========================================================================
// TAREFA 1: Aquisição Serial (CORE 0)
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
// TAREFA 2: Processamento Digital de Imagem - PDI (CORE 1)
// =========================================================================
void processImageTask(void *pvParameters) {
    int dx[8] = {0, 1, 2, 2, 2, 1, 0, 0};
    int dy[8] = {0, 0, 0, 1, 2, 2, 2, 1};
    int tamanhoRegiao = 3 * BLOCO;

    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // 1. Criar Imagem Integral (Mais rápido que acessar pixels um a um)
        for (int y = 1; y <= HEIGHT; y++) {
            for (int x = 1; x <= WIDTH; x++) {
                integralImage[y][x] = inputImage[y - 1][x - 1]
                    + integralImage[y - 1][x] + integralImage[y][x - 1]
                    - integralImage[y - 1][x - 1];
            }
        }

        // 2. Extração MB-LBP
        memset(resultadoLBP, 0, sizeof(resultadoLBP)); // Limpa a matriz
        for (int y = 0; y <= HEIGHT - tamanhoRegiao; y++) {
            for (int x = 0; x <= WIDTH - tamanhoRegiao; x++) {
                int cx = x + BLOCO; int cy = y + BLOCO;
                int somaCentro = somaBloco(cx, cy, BLOCO);
                uint8_t codigo = 0;
                
                for (int i = 0; i < 8; i++) {
                    if (somaBloco(x + dx[i]*BLOCO, y + dy[i]*BLOCO, BLOCO) >= somaCentro) {
                        codigo |= (1 << i);
                    }
                }
                resultadoLBP[y + tamanhoRegiao/2][x + tamanhoRegiao/2] = codigo;
            }
        }

        // 3. Calcular Histograma LBPH (Vetor de 6400 posições)
        memset(vetorLBPH, 0, sizeof(vetorLBPH));
        int wBloco = WIDTH / GRID_X;
        int hBloco = HEIGHT / GRID_Y;

        for (int gy = 0; gy < GRID_Y; gy++) {
            for (int gx = 0; gx < GRID_X; gx++) {
                int offset = (gy * GRID_X + gx) * 256;
                int xFim = (gx == GRID_X - 1) ? WIDTH : (gx + 1) * wBloco;
                int yFim = (gy == GRID_Y - 1) ? HEIGHT : (gy + 1) * hBloco;

                for (int y = gy * hBloco; y < yFim; y++) {
                    for (int x = gx * wBloco; x < xFim; x++) {
                        vetorLBPH[offset + resultadoLBP[y][x]]++;
                    }
                }
            }
        }

        // 4. Classificação com Distância Euclidiana
        double menorDistancia = 9999999.0;
        
        for (int i = 0; i < NUM_ROSTOS; i++) {
            double distAtual = calcularDistanciaEuclidiana(vetorLBPH, banco_rostos[i]);
            if (distAtual < menorDistancia) {
                menorDistancia = distAtual;
            }
        }

        // Limiar provisório - você precisará calibrar isso vendo o terminal
        double threshold = 50.0; 
        bool ehOAluno = (menorDistancia <= threshold);

        // 5. ESP-NOW e Feedback
        dadosEnvio.reconhecido = ehOAluno;
        esp_now_send(macESP2, (uint8_t *) &dadosEnvio, sizeof(dadosEnvio));

        if (ehOAluno) {
            Serial.printf("ACESSO LIBERADO! (Distancia: %.2f)\n", menorDistancia);
        } else {
            Serial.printf("ACESSO NEGADO (Distancia: %.2f)\n", menorDistancia);
        }
        
        Serial.println("OK"); // Libera o Python para o próximo frame
    }
}

// =========================================================================
void setup() {
    Serial.begin(115200);
    Serial.setTimeout(500); 

    WiFi.mode(WIFI_STA);
    if (esp_now_init() != ESP_OK) return;

    memcpy(peerInfo.peer_addr, macESP2, 6);
    peerInfo.channel = 0;  
    peerInfo.encrypt = false;
    esp_now_add_peer(&peerInfo);

    xTaskCreatePinnedToCore(receiveSerialTask, "RxTask", 4096, NULL, 1, NULL, 0);
    xTaskCreatePinnedToCore(processImageTask, "ProcTask", 8192, NULL, 2, &TaskProcess_Handle, 1);
}

void loop() { vTaskDelete(NULL); }