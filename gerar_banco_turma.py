import cv2
import numpy as np
import os
import glob
import re

# Configurações otimizadas para a ESP32
WIDTH = 64
HEIGHT = 64
BLOCO = 3
GRID_X = 5
GRID_Y = 5
TAM_REGIAO = 3 * BLOCO
BINS = 256
TAMANHO_VETOR = GRID_X * GRID_Y * BINS

def extrair_nome(caminho_arquivo):
    # Pega só o nome do arquivo (ex: "Andre_20260929_151219_479671.jpg")
    nome_base = os.path.basename(caminho_arquivo)
    # Tira a extensão
    nome_base = os.path.splitext(nome_base)[0]
    # Corta a partir do ano "_202"
    nome_base = re.split(r'_202', nome_base)[0]
    # Remove qualquer número que sobrou (ex: iara1 -> iara)
    nome_base = re.sub(r'\d+', '', nome_base)
    return nome_base.lower()

def soma_bloco(integral, x, y, tamanho):
    # A mesma lógica exata de soma de matriz integral do C++
    return (int(integral[y + tamanho, x + tamanho]) 
          - int(integral[y, x + tamanho]) 
          - int(integral[y + tamanho, x]) 
          + int(integral[y, x]))

def extrair_lbph(img_gray):
    # 1. Imagem Integral
    integral = cv2.integral(img_gray)
    resultado = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    
    dx = [0, 1, 2, 2, 2, 1, 0, 0]
    dy = [0, 0, 0, 1, 2, 2, 2, 1]
    
    # 2. MB-LBP
    for y in range(HEIGHT - TAM_REGIAO + 1):
        for x in range(WIDTH - TAM_REGIAO + 1):
            cx, cy = x + BLOCO, y + BLOCO
            soma_centro = soma_bloco(integral, cx, cy, BLOCO)
            codigo = 0
            
            for i in range(8):
                nx, ny = x + dx[i]*BLOCO, y + dy[i]*BLOCO
                if soma_bloco(integral, nx, ny, BLOCO) >= soma_centro:
                    codigo |= (1 << i)
                    
            resultado[y + TAM_REGIAO//2, x + TAM_REGIAO//2] = codigo

    # 3. Histograma 5x5
    vetor_lbph = np.zeros(TAMANHO_VETOR, dtype=np.float64)
    w_bloco = WIDTH // GRID_X
    h_bloco = HEIGHT // GRID_Y
    
    for gy in range(GRID_Y):
        for gx in range(GRID_X):
            offset = (gy * GRID_X + gx) * BINS
            x_inicio = gx * w_bloco
            y_inicio = gy * h_bloco
            x_fim = WIDTH if gx == GRID_X - 1 else (gx + 1) * w_bloco
            y_fim = HEIGHT if gy == GRID_Y - 1 else (gy + 1) * h_bloco
            
            bloco_recorte = resultado[y_inicio:y_fim, x_inicio:x_fim]
            hist, _ = np.histogram(bloco_recorte, bins=256, range=(0, 256))
            vetor_lbph[offset : offset + BINS] = hist
            
    return vetor_lbph

# =====================================================================
# INÍCIO DO PROCESSAMENTO
# =====================================================================
print("Lendo imagens da turma e extraindo características...")

# Dicionário para agrupar as fotos por pessoa (K-means / Média)
agrupamento_pessoas = {}

# Puxa todas as imagens da pasta
arquivos = glob.glob("imagens/*.jpg") + glob.glob("imagens/*.jpeg")

if not arquivos:
    print("ERRO: Nenhuma imagem encontrada na pasta 'imagens/'.")
    exit()

for arquivo in arquivos:
    nome = extrair_nome(arquivo)
    
    # Lê a imagem e converte para tons de cinza
    img = cv2.imread(arquivo, cv2.IMREAD_GRAYSCALE)
    if img is None:
        continue
        
    # O SEGREDO DO TEMPO REAL: Redimensionar para 64x64 antes de treinar
    img_redimensionada = cv2.resize(img, (WIDTH, HEIGHT))
    
    # Extrai o vetor LBP de 6400 posições
    vetor = extrair_lbph(img_redimensionada)
    
    if nome not in agrupamento_pessoas:
        agrupamento_pessoas[nome] = []
    agrupamento_pessoas[nome].append(vetor)
    
    print(f"Processado: {nome} ({arquivo})")

# =====================================================================
# GERANDO O ARQUIVO .H PARA A ESP32
# =====================================================================
print("\nCalculando os centroides (Médias) e gerando banco_rostos.h...")

# Coloque aqui o caminho exato da pasta do seu projeto da ESP32
caminho_esp32 = r"C:\Users\amand\OneDrive\Documentos\GitHub\reconhecimento-facial\esp-main\banco_rostos.h"

with open(caminho_esp32, "w") as f:
    f.write("#ifndef BANCO_ROSTOS_H\n#define BANCO_ROSTOS_H\n\n")
    f.write("#include <Arduino.h>\n\n")
    f.write(f"const int NUM_ROSTOS = {len(agrupamento_pessoas)};\n\n")
    
    nomes = list(agrupamento_pessoas.keys())
    
    # Nomes
    f.write("const char nomes_rostos[][256] = {\n")
    for i, nome in enumerate(nomes):
        f.write(f'    "{nome}"')
        f.write(",\n" if i < len(nomes)-1 else "\n")
    f.write("};\n\n")
    
    # Matriz 2D de doubles
    f.write("const double banco_rostos[][6400] = {\n")
    for i, nome in enumerate(nomes):
        # Aqui fazemos a função do "kmeans.c": a média de todas as fotos da pessoa
        centroide = np.mean(agrupamento_pessoas[nome], axis=0)
        
        f.write("    {\n        ")
        valores_str = [f"{val:.1f}" for val in centroide]
        
        # Quebra a linha a cada 20 números para a Arduino IDE não travar
        for j in range(0, len(valores_str), 20):
            linha_valores = ", ".join(valores_str[j:j+20])
            if j + 20 >= len(valores_str):
                f.write(linha_valores)
            else:
                f.write(linha_valores + ",\n        ")
                
        f.write("\n    }")
        f.write(",\n" if i < len(nomes)-1 else "\n")
        
    f.write("};\n\n#endif\n")

print(f"\nSUCESSO! Arquivo salvo em: {caminho_esp32}")
print(f"Total de perfis únicos consolidados: {len(agrupamento_pessoas)}")