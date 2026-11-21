import cv2
import serial
import time
import sys
import threading
import numpy as np

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
# CONFIGURAÇÕES INICIAIS
# =========================================================================
SERIAL_PORT = 'COM7' 
BAUD_RATE = 115200
WIDTH = 64
HEIGHT = 64

frame_para_enviar = None
rodando = True

# Dicionário compartilhado entre as threads para atualizar a tela
info_acesso = {
    "status": None,  # True (Liberado), False (Negado) ou None (Aguardando)
    "nome": "Analisando..."
}

try:
    esp_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5)
    print(f"Sucesso: Conectado a {SERIAL_PORT}")
except Exception as e:
    print(f"Erro ao abrir a porta serial.\n{e}")
    sys.exit()

time.sleep(2)

# =========================================================================
# THREAD SECUNDÁRIA: Comunicação Serial com a ESP32
# =========================================================================
def thread_comunicacao_esp():
    global frame_para_enviar, rodando, info_acesso
    while rodando:
        if frame_para_enviar is not None:
            frame_atual = frame_para_enviar.copy()
            image_bytes = frame_atual.flatten().tobytes()
            
            try:
                # Envia a foto
                esp_serial.write(b'S')
                esp_serial.write(image_bytes)
                
                # Lê a resposta
                resposta = esp_serial.readline().decode('utf-8', errors='ignore').strip()
                
                if resposta:
                    print(f"ESP32 respondeu: {resposta}")
                    
                    if "ACESSO LIBERADO" in resposta:
                        info_acesso["status"] = True
                        try:
                            nome = resposta.split("como: ")[1].split(" (")[0]
                            info_acesso["nome"] = nome
                        except:
                            info_acesso["nome"] = "Autorizado"
                            
                    elif "ACESSO NEGADO" in resposta:
                        info_acesso["status"] = False
                        info_acesso["nome"] = "Nao identificado"
                        
                    if "ACESSO" in resposta:
                        _ = esp_serial.readline()
            except Exception as e:
                # Se a porta for fechada abruptamente, apenas sai silenciosamente
                break
        else:
            info_acesso["status"] = None
            info_acesso["nome"] = "Analisando..."
            time.sleep(0.1)

thread_esp = threading.Thread(target=thread_comunicacao_esp)
thread_esp.start()

# =========================================================================
# THREAD PRINCIPAL: Rastreamento e Interface Gráfica
# =========================================================================
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)

print("Sistema iniciado. Pressione 'q' para sair.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        
        # Processamento e envio
        rosto_cortado = gray_frame[y:y+h, x:x+w]
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        imagem_iluminada = aplicar_tan_triggs(resized)
        frame_para_enviar = imagem_iluminada

        # -------------------------------------------------------------
        # LÓGICA DE CORES DA INTERFACE
        # -------------------------------------------------------------
        if info_acesso["status"] is True:
            cor = (0, 255, 0) # Verde (BGR)
        elif info_acesso["status"] is False:
            cor = (0, 0, 255) # Vermelho (BGR)
        else:
            cor = (255, 0, 0) # Azul (Aguardando processamento)
            
        texto = info_acesso["nome"]

        # Desenha a moldura e o fundo preto para o texto
        cv2.rectangle(frame, (x, y), (x+w, y+h), cor, 2)
        cv2.rectangle(frame, (x, y-35), (x+w, y), cor, cv2.FILLED)
        
        # Escreve o texto em branco por cima da tarja
        cv2.putText(frame, texto, (x + 5, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # (Opcional) Pode comentar a linha abaixo se quiser esconder a visão da ESP32 na apresentação
        cv2.imshow("Visao Interna da ESP32", imagem_iluminada)
    else:
        frame_para_enviar = None

    cv2.imshow("Acesso LabWare", frame)

    if cv2.waitKey(30) & 0xFF == ord('q'):
        rodando = False
        break

cap.release()
esp_serial.close()
cv2.destroyAllWindows()
thread_esp.join()