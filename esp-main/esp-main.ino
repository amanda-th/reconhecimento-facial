#include <Arduino.h>
#include <math.h>
#include <WiFi.h>
#include <esp_now.h>

#include "banco_rostos.h" 

// =========================================================================
// CONFIGURAÇÕES DO LBP DA TURMA
// =========================================================================
#define BLOCO 3
#define GRID_X 5
#define GRID_Y 5
#define BINS 59 // Novo padrão uniforme
#define TAMANHO_VETOR 1475 // 25 blocos * 59 bins

#define WIDTH 64
#define HEIGHT 64
#define FRAME_SIZE (WIDTH * HEIGHT)

// Matriz de pesos 5x5 (Multiplicadores para cada região do rosto)
const float PESOS_REGIAO[25] = {
    0.5, 1.0, 1.0, 1.0, 0.5, // Linha 0: Testa (fundo e cabelo atrapalham nas bordas)
    0.5, 2.0, 2.0, 2.0, 0.5, // Linha 1: Olhos e sobrancelhas (Alta importância)
    0.5, 2.0, 2.0, 2.0, 0.5, // Linha 2: Nariz e centro do rosto (Alta importância)
    0.5, 1.5, 1.5, 1.5, 0.5, // Linha 3: Boca (Média importância, muda se a pessoa sorrir)
    0.2, 0.5, 0.5, 0.5, 0.2  // Linha 4: Queixo, barba e pescoço (Área de maior ruído, peso esmagado)
};

// Matrizes globais para processamento na RAM
uint8_t inputImage[HEIGHT][WIDTH];
int integralImage[HEIGHT + 1][WIDTH + 1];
uint8_t resultadoLBP[HEIGHT][WIDTH];
int vetorLBPH[TAMANHO_VETOR];
float vetorLBPH_norm[TAMANHO_VETOR]; // Novo vetor normalizado

// MAC Address da segunda ESP32 (Atuador)
uint8_t macESP2[] = {0x20, 0x9B, 0xA9, 0x8F, 0xFC, 0xE4}; 

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

// Distância Qui-Quadrado com Pesos (Weighted Chi-Square)
double calcularDistanciaChi2Ponderada(float *vetorNovaFoto, const double *vetorAmostra) {
    double dist = 0.0;
    for (int i = 0; i < TAMANHO_VETOR; i++) {
        double a = vetorNovaFoto[i];
        double b = vetorAmostra[i];
        
        if (a + b > 1e-9) {
            // Descobre em qual das 25 células (0 a 24) estamos lendo agora
            int celulaAtual = i / BINS; 
            float peso = PESOS_REGIAO[celulaAtual];
            
            // Aplica o peso na diferença daquele histograma
            dist += peso * (((a - b) * (a - b)) / (a + b));
        }
    }
    return dist;
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

        // 1. Criar Imagem Integral
        for (int y = 1; y <= HEIGHT; y++) {
            for (int x = 1; x <= WIDTH; x++) {
                integralImage[y][x] = inputImage[y - 1][x - 1]
                    + integralImage[y - 1][x] + integralImage[y][x - 1]
                    - integralImage[y - 1][x - 1];
            }
        }

        // 2. Extração MB-LBP
        memset(resultadoLBP, 0, sizeof(resultadoLBP)); 
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
                // Converte direto pela lookup table gerada pelo Python!
                resultadoLBP[y + tamanhoRegiao/2][x + tamanhoRegiao/2] = TAB59[codigo];
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2));

        // 3. Calcular Histograma e Normalizar (L1)
        memset(vetorLBPH, 0, sizeof(vetorLBPH));
        int wBloco = WIDTH / GRID_X;
        int hBloco = HEIGHT / GRID_Y;

        // Monta as contagens
        for (int gy = 0; gy < GRID_Y; gy++) {
            for (int gx = 0; gx < GRID_X; gx++) {
                int offset = (gy * GRID_X + gx) * BINS;
                int xFim = (gx == GRID_X - 1) ? WIDTH : (gx + 1) * wBloco;
                int yFim = (gy == GRID_Y - 1) ? HEIGHT : (gy + 1) * hBloco;

                for (int y = gy * hBloco; y < yFim; y++) {
                    for (int x = gx * wBloco; x < xFim; x++) {
                        vetorLBPH[offset + resultadoLBP[y][x]]++;
                    }
                }
                
                // Normaliza a célula (divide tudo pela soma daquele quadrado)
                float soma = 0;
                for (int i = 0; i < BINS; i++) soma += vetorLBPH[offset + i];
                for (int i = 0; i < BINS; i++) {
                    vetorLBPH_norm[offset + i] = (soma > 0) ? (float)vetorLBPH[offset + i] / soma : 0.0;
                }
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2));

        // 4. Classificação com Amostra Mais Próxima (Nearest Neighbor) e Qui-Quadrado Ponderado
        double menorDistancia = 9999999.0;
        int idIdentificado = 0; 
        
        // Varre todas as fotos isoladas do banco
        for (int i = 0; i < NUM_AMOSTRAS; i++) {
            double distAtual = calcularDistanciaChi2Ponderada(vetorLBPH_norm, banco_rostos[i]);
            
            if (distAtual < menorDistancia) {
                menorDistancia = distAtual;
                // Busca a qual pessoa essa foto específica pertence
                idIdentificado = labels_rostos[i]; 
            }
            
            // Respiramos a cada 20 fotos comparadas
            if (i % 20 == 0) vTaskDelay(pdMS_TO_TICKS(1));
        }

        // O limiar com Qui-Quadrado + Pesos fica ajustado para a mesma faixa de segurança rigorosa
        double threshold = 7.5;
        bool ehOAluno = (menorDistancia <= threshold);

        // 5. ESP-NOW e Feedback
        dadosEnvio.reconhecido = ehOAluno;
        esp_now_send(macESP2, (uint8_t *) &dadosEnvio, sizeof(dadosEnvio));

        if (NUM_AMOSTRAS > 0) {
            if (ehOAluno) {
                Serial.printf("ACESSO LIBERADO! Identificado como: %s (Distancia: %.2f)\n", nomes_rostos[idIdentificado], menorDistancia);
            } else {
                Serial.printf("ACESSO NEGADO! (Parecido com %s, dist: %.2f)\n", nomes_rostos[idIdentificado], menorDistancia);
            }
        }
        
        Serial.println("OK"); 
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