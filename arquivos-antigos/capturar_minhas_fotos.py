import cv2
import os
import sys
import numpy as np
import tkinter as tk
from tkinter import simpledialog

# =========================================================================
# FUNÇÃO DO ARTIGO: Tan & Triggs
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

# =========================================================================
# CONFIGURAÇÕES INICIAIS & POPUP DE NOME
# =========================================================================
WIDTH = 64
HEIGHT = 64

# Cria uma janela base invisível do Tkinter
root = tk.Tk()
root.withdraw() 

# Abre a janelinha de popup nativa do sistema
nome_usuario = simpledialog.askstring("Cadastro de Rosto", "Digite o nome do usuário (sem espaços):")

# Trava de segurança: se fechar o popup sem digitar, encerra o programa
if not nome_usuario:
    print("Operação cancelada pelo usuário.")
    sys.exit()

nome_usuario = nome_usuario.strip()

# Salva diretamente na pasta final já processada
pasta = 'imagens_processadas'
if not os.path.exists(pasta):
    os.makedirs(pasta)

# Carrega a IA de detecção do OpenCV
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

cap = cv2.VideoCapture(0)
# ... O resto do script continua exatamente igual a partir daqui ...

cap = cv2.VideoCapture(0)
print(f"\nBem-vindo(a), {nome_usuario}! Pressione 'c' para capturar.")
print("Tire de 5 a 10 fotos variando ligeiramente o angulo e a expressao.")
print("Pressione 'q' para sair.")

contador = 1
while True:
    ret, frame = cap.read()
    if not ret:
        print("Erro ao ler o frame da câmera.")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Rastreamento dinâmico
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    imagem_processada = None

    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        
        # 1. Recorta o rosto
        rosto_cortado = gray[y:y+h, x:x+w]
        
        # 2. Redimensiona para o tamanho estrito da matriz em C++
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        
        # 3. Aplica o filtro de normalização de iluminação
        imagem_processada = aplicar_tan_triggs(resized)
        
        # Desenha o quadrado verde acompanhando o rosto
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        
        # Mostra o resultado final que irá para a ESP32
        cv2.imshow("O que a ESP32 vai aprender (64x64 Tratado)", imagem_processada)
    
    # Mostra a tela global
    cv2.imshow("Visao Geral com Rastreamento", frame)

    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('c'):
        if imagem_processada is not None:
            # Salva o frame já tratado (64x64, cinza, filtro aplicado)
            nome_arquivo = os.path.join(pasta, f"{nome_usuario}_{contador}.jpg")
            cv2.imwrite(nome_arquivo, imagem_processada)
            print(f"[OK] Foto salva: {nome_arquivo}")
            contador += 1
        else:
            print("[AVISO] Nenhum rosto detectado! Posicione-se no quadro.")
            
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()