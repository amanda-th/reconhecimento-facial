import cv2
import os
import sys
import numpy as np
import glob
import re
import tkinter as tk
from tkinter import simpledialog

# =========================================================================
# CONFIGURAÇÕES GERAIS
# =========================================================================
WIDTH = 64
HEIGHT = 64
BLOCO = 3
GRID_X = 5
GRID_Y = 5
TAM_REGIAO = 3 * BLOCO
BINS = 256
TAMANHO_VETOR = GRID_X * GRID_Y * BINS

# os.path.join resolve as barras invertidas (\) ou normais (/) automaticamente.
pasta_processadas = 'imagens_processadas'
caminho_esp32 = os.path.join('esp-main', 'banco_rostos.h') # Assume que a pasta esp-main tá no mesmo diretório do projeto

if not os.path.exists(pasta_processadas):
    os.makedirs(pasta_processadas)

# =========================================================================
# FUNÇÕES MATEMÁTICAS (Tan & Triggs + LBP)
# =========================================================================
def aplicar_tan_triggs(imagem_cortada):
    gamma = 0.2
    img_float = imagem_cortada.astype(np.float32) / 255.0
    img_gama = np.power(img_float, gamma) * 255.0
    
    blur1 = cv2.GaussianBlur(img_gama, (0, 0), 1.0)
    blur2 = cv2.GaussianBlur(img_gama, (0, 0), 2.0)
    dog = blur1 - blur2
    
    dog_normalizado = cv2.normalize(dog, None, 0, 255, cv2.NORM_MINMAX)
    dog_uint8 = dog_normalizado.astype(np.uint8)
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    return clahe.apply(dog_uint8)

def extrair_nome(caminho_arquivo):
    nome_base = os.path.basename(caminho_arquivo)
    nome_base = os.path.splitext(nome_base)[0]
    nome_base = re.sub(r'_\d+$', '', nome_base) # Tira o _1, _2 do final
    nome_base = re.split(r'_202', nome_base)[0]
    nome_base = re.sub(r'\d+', '', nome_base)
    return nome_base.lower()

def soma_bloco(integral, x, y, tamanho):
    return (int(integral[y + tamanho, x + tamanho]) - int(integral[y, x + tamanho]) - 
            int(integral[y + tamanho, x]) + int(integral[y, x]))

def extrair_lbph(img_gray):
    integral = cv2.integral(img_gray)
    resultado = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    
    dx = [0, 1, 2, 2, 2, 1, 0, 0]
    dy = [0, 0, 0, 1, 2, 2, 2, 1]
    
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

    vetor_lbph = np.zeros(TAMANHO_VETOR, dtype=np.float64)
    w_bloco, h_bloco = WIDTH // GRID_X, HEIGHT // GRID_Y
    
    for gy in range(GRID_Y):
        for gx in range(GRID_X):
            offset = (gy * GRID_X + gx) * BINS
            x_inicio, y_inicio = gx * w_bloco, gy * h_bloco
            x_fim = WIDTH if gx == GRID_X - 1 else (gx + 1) * w_bloco
            y_fim = HEIGHT if gy == GRID_Y - 1 else (gy + 1) * h_bloco
            
            bloco_recorte = resultado[y_inicio:y_fim, x_inicio:x_fim]
            hist, _ = np.histogram(bloco_recorte, bins=256, range=(0, 256))
            vetor_lbph[offset : offset + BINS] = hist
            
    return vetor_lbph

# =========================================================================
# PARTE 1: CAPTURA E SALVAMENTO
# =========================================================================
root = tk.Tk()
root.withdraw() 
nome_usuario = simpledialog.askstring("Cadastro", "Digite o nome do usuario (sem espacos):")

if not nome_usuario:
    print("Operação cancelada.")
    sys.exit()
nome_usuario = nome_usuario.strip()

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)

print(f"\n[1/3] CAPTURANDO FOTOS PARA: {nome_usuario}")
print("Pressione 'c' para tirar a foto (faça umas 5 ou 6). Pressione 'q' quando terminar.")

contador = 1
while True:
    ret, frame = cap.read()
    if not ret: break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
    imagem_processada = None

    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        rosto_cortado = gray[y:y+h, x:x+w]
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        imagem_processada = aplicar_tan_triggs(resized)
        
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow("Processado (ESP32)", imagem_processada)
    
    cv2.imshow("Captura", frame)
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('c') and imagem_processada is not None:
        nome_arquivo = os.path.join(pasta_processadas, f"{nome_usuario}_{contador}.jpg")
        cv2.imwrite(nome_arquivo, imagem_processada)
        print(f" -> Foto {contador} salva com sucesso!")
        contador += 1
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# =========================================================================
# PARTE 2: GERAÇÃO DO BANCO (Automático após fechar a câmera)
# =========================================================================
print("\n[2/3] CALCULANDO MATRIZES LBP DE TODA A TURMA...")

agrupamento_pessoas = {}
arquivos = (glob.glob(os.path.join(pasta_processadas, "*.jpg")) + 
            glob.glob(os.path.join(pasta_processadas, "*.jpeg")) + 
            glob.glob(os.path.join(pasta_processadas, "*.bmp")) + 
            glob.glob(os.path.join(pasta_processadas, "*.png")))

for arquivo in arquivos:
    nome = extrair_nome(arquivo)
    img = cv2.imread(arquivo, cv2.IMREAD_GRAYSCALE)
    if img is None: continue
    
    img_redimensionada = cv2.resize(img, (WIDTH, HEIGHT))
    vetor = extrair_lbph(img_redimensionada)
    
    if nome not in agrupamento_pessoas:
        agrupamento_pessoas[nome] = []
    agrupamento_pessoas[nome].append(vetor)

# =========================================================================
# PARTE 3: CRIANDO O .H
# =========================================================================
print(f"\n[3/3] GERANDO ARQUIVO C++ EM: {caminho_esp32}")

try:
    with open(caminho_esp32, "w") as f:
        f.write("#ifndef BANCO_ROSTOS_H\n#define BANCO_ROSTOS_H\n\n#include <Arduino.h>\n\n")
        f.write(f"const int NUM_ROSTOS = {len(agrupamento_pessoas)};\n\n")
        
        nomes = list(agrupamento_pessoas.keys())
        f.write("const char nomes_rostos[][256] = {\n")
        for i, nome in enumerate(nomes):
            f.write(f'    "{nome}"' + (",\n" if i < len(nomes)-1 else "\n"))
        f.write("};\n\n")
        
        f.write("const double banco_rostos[][6400] = {\n")
        for i, nome in enumerate(nomes):
            centroide = np.mean(agrupamento_pessoas[nome], axis=0)
            f.write("    {\n        ")
            valores_str = [f"{val:.1f}" for val in centroide]
            for j in range(0, len(valores_str), 20):
                linha_valores = ", ".join(valores_str[j:j+20])
                if j + 20 >= len(valores_str):
                    f.write(linha_valores)
                else:
                    f.write(linha_valores + ",\n        ")
            f.write("\n    }" + (",\n" if i < len(nomes)-1 else "\n"))
        f.write("};\n\n#endif\n")
        
    print("\n" + "="*50)
    print("(!) CADASTRO E BANCO DE DADOS CONCLUIDOS!")
    print(f"Total de pessoas na base: {len(agrupamento_pessoas)}")
    print("="*50)
    print("-> PROXIMO PASSO:")
    print("1. Abra a Arduino IDE e clique em 'Carregar' (Upload).")
    print("2. Rode o arquivo 'cam.py' para testar.")

except Exception as e:
    print(f"ERRO ao tentar salvar na pasta 'esp-main': {e}")
    print("Verifique se a pasta 'esp-main' está no mesmo lugar que este script.")