import cv2
import serial
import time
import sys
import threading
import numpy as np
import csv
import os
from datetime import datetime

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
# CONFIGURAÇÕES INICIAIS E SISTEMA DE LOG (CSV)
# =========================================================================

# No linux SERIAL_PORT = '/dev/ttyUSB0' ou /dev/ttyACM0, dependendo da placa
SERIAL_PORT = '/dev/ttyUSB1' 
BAUD_RATE = 115200
WIDTH = 64
HEIGHT = 64

frame_para_enviar = None
rodando = True
ultimo_log_tempo = 0

arquivo_csv = 'relatorio_acessos.csv'
if not os.path.exists(arquivo_csv):
    with open(arquivo_csv, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Data_Hora', 'Nome', 'Status', 'Distancia_LBP'])

def registrar_log(nome, status, distancia):
    global ultimo_log_tempo
    agora = time.time()
    if agora - ultimo_log_tempo > 3.0:
        with open(arquivo_csv, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([data_hora, nome, status, round(distancia, 2)])
        ultimo_log_tempo = agora

info_acesso = {
    "status": None,  
    "nome": "Analisando...",
    "distancia": 0.0,
    "tempo_liberacao": 0.0
}

contador_reconhecimento = 0 

try:
    esp_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5)
    print(f"Sucesso: Conectado a {SERIAL_PORT}")
except Exception as e:
    print(f"Erro ao abrir a porta serial.\n{e}")
    sys.exit()

time.sleep(2)

# =========================================================================
# THREAD SECUNDÁRIA: Comunicação Serial
# =========================================================================
def thread_comunicacao_esp():
    global frame_para_enviar, rodando, info_acesso, contador_reconhecimento
    while rodando:
        if frame_para_enviar is not None:
            frame_atual = frame_para_enviar.copy()
            image_bytes = frame_atual.flatten().tobytes()
            
            try:
                esp_serial.write(b'S')
                esp_serial.write(image_bytes)
                
                resposta = esp_serial.readline().decode('utf-8', errors='ignore').strip()
                
                if resposta:
                    agora = time.time()
                    porta_fisica_aberta = (agora - info_acesso["tempo_liberacao"] < 5.0)

                    if "ACESSO LIBERADO" in resposta:
                        contador_reconhecimento += 1
                        
                        if contador_reconhecimento >= 3:
                            info_acesso["status"] = True
                            info_acesso["tempo_liberacao"] = agora 
                            
                            try:
                                info_acesso["nome"] = resposta.split("como: ")[1].split(" (")[0]
                                info_acesso["distancia"] = float(resposta.split("Distancia: ")[1].split(")")[0])
                            except: pass
                            
                            if not porta_fisica_aberta:
                                registrar_log(info_acesso["nome"], "LIBERADO", info_acesso["distancia"])
                            
                    elif "ACESSO NEGADO" in resposta:
                        contador_reconhecimento = 0 
                        
                        if not porta_fisica_aberta:
                            info_acesso["status"] = False
                            try:
                                info_acesso["nome"] = resposta.split("com ")[1].split(",")[0]
                                info_acesso["distancia"] = float(resposta.split("dist: ")[1].split(")")[0])
                            except: pass
                            
                            registrar_log(info_acesso["nome"], "BARRADO", info_acesso["distancia"])
                        
                    if "ACESSO" in resposta:
                        _ = esp_serial.readline()
                        
            except Exception as e:
                break
        else:
            contador_reconhecimento = 0
            if time.time() - info_acesso["tempo_liberacao"] > 5.0:
                info_acesso["status"] = None
                info_acesso["nome"] = "Analisando..."
                info_acesso["distancia"] = 0.0
            time.sleep(0.1)

thread_esp = threading.Thread(target=thread_comunicacao_esp)
thread_esp.start()

# =========================================================================
# THREAD PRINCIPAL: Rastreamento e HUD
# =========================================================================
# Acha a pasta exata onde este script está rodando
pasta_script = os.path.dirname(os.path.abspath(__file__))
caminho_cascade = os.path.join(pasta_script, 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)
face_cascade = cv2.CascadeClassifier(caminho_cascade)

print("Sistema de Segurança Iniciado. Pressione 'q' para sair.")
tempo_anterior = time.time()

# Cria o quadro preto inicial para a miniatura (PiP)
tamanho_pip = 128
pip_atual = np.zeros((tamanho_pip, tamanho_pip, 3), dtype=np.uint8)
cv2.putText(pip_atual, "SEM ROSTO", (25, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

while True:
    ret, frame = cap.read()
    if not ret: 
        print("\n[ERRO FATAL] A câmera travou ou desconectou!")
        break

    tempo_atual = time.time()
    fps = 1 / (tempo_atual - tempo_anterior) if (tempo_atual - tempo_anterior) > 0 else 30
    tempo_anterior = tempo_atual

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        
        rosto_cortado = gray_frame[y:y+h, x:x+w]
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        imagem_iluminada = aplicar_tan_triggs(resized)
        frame_para_enviar = imagem_iluminada

        # Atualiza a miniatura (PiP) com o rosto processado
        pip_bgr = cv2.cvtColor(imagem_iluminada, cv2.COLOR_GRAY2BGR)
        pip_atual = cv2.resize(pip_bgr, (tamanho_pip, tamanho_pip))

        # Lógica de sincronia dos 5 segundos da placa
        if info_acesso["status"] is True and (time.time() - info_acesso["tempo_liberacao"] > 5.0):
            info_acesso["status"] = None
            info_acesso["nome"] = "Trancando..."

        # Cores e Textos
        if info_acesso["status"] is True:
            cor = (100, 220, 50)
            texto_status = "AUTORIZADO"
        elif info_acesso["status"] is False:
            cor = (0, 0, 255)
            texto_status = "BLOQUEADO"
        else:
            cor = (255, 150, 0)
            texto_status = "PROCESSANDO..."
            
        texto_nome = info_acesso["nome"].upper()
        texto_dist = f"Match Dist: {info_acesso['distancia']:.1f}"

        # HUD do Rosto
        cv2.rectangle(frame, (x, y), (x+w, y+h), cor, 2)
        cx, cy = x + w // 2, y + h // 2
        cv2.line(frame, (cx - 15, cy), (cx + 15, cy), cor, 1)
        cv2.line(frame, (cx, cy - 15), (cx, cy + 15), cor, 1)
        cv2.circle(frame, (cx, cy), 3, cor, -1)

        cv2.rectangle(frame, (x, y-45), (x+w, y), cor, cv2.FILLED)
        cv2.putText(frame, texto_status, (x + 5, y - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)
        cv2.putText(frame, texto_nome, (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.rectangle(frame, (x, y+h), (x+w, y+h+25), cor, cv2.FILLED)
        cv2.putText(frame, texto_dist, (x + 5, y + h + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)
        
    else:
        frame_para_enviar = None
        # Se perdeu o rosto, volta o PiP para a tela preta "SEM ROSTO"
        pip_atual = np.zeros((tamanho_pip, tamanho_pip, 3), dtype=np.uint8)
        cv2.putText(pip_atual, "SEM ROSTO", (25, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


    # Adiciona a miniatura PiP no canto direito
    H, W = frame.shape[:2]
    x_pip = W - tamanho_pip - 20
    y_pip = 20
    frame[y_pip:y_pip+tamanho_pip, x_pip:x_pip+tamanho_pip] = pip_atual
    cv2.rectangle(frame, (x_pip, y_pip), (x_pip+tamanho_pip, y_pip+tamanho_pip), (255, 255, 255), 1)
    cv2.putText(frame, "VISAO ESP32", (x_pip, y_pip - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    # Textos globais de sistema
    data_hora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(frame, f"SYS: UERGS Access Control", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 220, 50), 2)
    cv2.putText(frame, f"DATA: {data_hora_str}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 220, 50), 1)
    cv2.putText(frame, f"FPS: {int(fps)}", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 220, 50), 1)

    # OS COMANDOS QUE MOSTRAM A TELA E FECHAM NO 'Q'
    cv2.imshow("Monitoramento de Acesso UERGS", frame)

    if cv2.waitKey(30) & 0xFF == ord('q'):
        rodando = False
        break

cap.release()
esp_serial.close()
cv2.destroyAllWindows()
thread_esp.join()