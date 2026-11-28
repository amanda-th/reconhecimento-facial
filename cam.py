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
# FUNÇÃO: Tan & Triggs
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
# CONFIGURAÇÕES E TEMPOS DA ESP32 ATUADORA
# =========================================================================
SERIAL_PORT = 'COM7' 
BAUD_RATE = 115200
WIDTH = 64
HEIGHT = 64

TEMPO_MOVIMENTO_SERVO = 0.5   # 500 ms
TEMPO_PERMANENCIA = 5.0       # 5000 ms
TEMPO_COOLDOWN = 3.0         # 3000 ms ("ESP surda" apos fechar)
CONFIRMACOES_NECESSARIAS = 3  # Alinhado com FOTOS_NECESSARIAS = 3 na ESP32 atuadora

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

# Estados: "ANALISANDO", "LIBERADO", "NEGADO"
info_acesso = {
    "estado": "ANALISANDO",
    "nome": "Analisando...",
    "distancia": 0.0,
    "inicio_liberacao": 0.0,
    "confirmacoes_atuais": 0
}
contador_reconhecimento = 0

try:
    esp_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
    print(f"Sucesso: Conectado a {SERIAL_PORT}")
except Exception as e:
    print(f"Erro ao abrir a porta serial.\n{e}")
    sys.exit()

time.sleep(2)

# =========================================================================
# THREAD: Comunicação Serial
# =========================================================================
def thread_comunicacao_esp():
    global frame_para_enviar, rodando, info_acesso, contador_reconhecimento
    while rodando:
        agora = time.time()
        elapsed = agora - info_acesso["inicio_liberacao"] if info_acesso["inicio_liberacao"] > 0 else 999.0
        duracao_aberta = TEMPO_MOVIMENTO_SERVO + TEMPO_PERMANENCIA
        duracao_total_ciclo = duracao_aberta + TEMPO_MOVIMENTO_SERVO + TEMPO_COOLDOWN

        em_ciclo_ativo = (elapsed < duracao_total_ciclo)

        if frame_para_enviar is not None:
            image_bytes = frame_para_enviar.copy().flatten().tobytes()
            
            try:
                esp_serial.reset_input_buffer()
                esp_serial.write(b'S')
                esp_serial.write(image_bytes)
                
                resposta = esp_serial.readline().decode('utf-8', errors='ignore').strip()
                
                if resposta:
                    agora = time.time()
                    elapsed = agora - info_acesso["inicio_liberacao"] if info_acesso["inicio_liberacao"] > 0 else 999.0
                    em_ciclo_ativo = (elapsed < duracao_total_ciclo)

                    if "ACESSO LIBERADO" in resposta:
                        if not em_ciclo_ativo:
                            contador_reconhecimento += 1
                            info_acesso["confirmacoes_atuais"] = contador_reconhecimento
                            try:
                                info_acesso["nome"] = resposta.split("como: ")[1].split(" (")[0]
                                info_acesso["distancia"] = float(resposta.split("Distancia: ")[1].split(")")[0])
                            except:
                                pass

                            if contador_reconhecimento >= CONFIRMACOES_NECESSARIAS:
                                info_acesso["estado"] = "LIBERADO"
                                info_acesso["inicio_liberacao"] = agora
                                contador_reconhecimento = 0
                                info_acesso["confirmacoes_atuais"] = 0
                                registrar_log(info_acesso["nome"], "LIBERADO", info_acesso["distancia"])
                            
                    elif "ACESSO NEGADO" in resposta:
                        contador_reconhecimento = 0
                        info_acesso["confirmacoes_atuais"] = 0
                        if not em_ciclo_ativo:
                            info_acesso["estado"] = "NEGADO"
                            try:
                                info_acesso["nome"] = resposta.split("com ")[1].split(",")[0]
                                info_acesso["distancia"] = float(resposta.split("dist: ")[1].split(")")[0])
                            except:
                                pass
                            registrar_log(info_acesso["nome"], "BARRADO", info_acesso["distancia"])
                        
            except Exception:
                break
        else:
            contador_reconhecimento = 0
            info_acesso["confirmacoes_atuais"] = 0
            if not em_ciclo_ativo:
                info_acesso["estado"] = "ANALISANDO"
                info_acesso["nome"] = "Analisando..."
                info_acesso["distancia"] = 0.0
            time.sleep(0.05)

thread_esp = threading.Thread(target=thread_comunicacao_esp)
thread_esp.start()

# =========================================================================
# THREAD PRINCIPAL: Câmera
# =========================================================================
pasta_script = os.path.dirname(os.path.abspath(__file__))
caminho_cascade = os.path.join(pasta_script, 'haarcascade_frontalface_default.xml')

cap = cv2.VideoCapture(0)

face_cascade = cv2.CascadeClassifier(caminho_cascade)
if face_cascade.empty():
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
if face_cascade.empty():
    print("\n[ERRO FATAL] O OpenCV não conseguiu carregar o arquivo XML de detecção facial.")
    sys.exit()

print("Sistema de Segurança Iniciado. Pressione 'q' para sair.")
tempo_anterior = time.time()
fps = 30.0

tamanho_pip = 128
pip_atual = np.zeros((tamanho_pip, tamanho_pip, 3), dtype=np.uint8)
cv2.putText(pip_atual, "SEM ROSTO", (25, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

duracao_aberta = TEMPO_MOVIMENTO_SERVO + TEMPO_PERMANENCIA
duracao_total_ciclo = duracao_aberta + TEMPO_MOVIMENTO_SERVO + TEMPO_COOLDOWN

while True:
    ret, frame = cap.read()
    if not ret: 
        print("\n[ERRO FATAL] A câmera travou ou desconectou!")
        break

    tempo_atual = time.time()
    dt = tempo_atual - tempo_anterior
    if dt > 0:
        fps = 1.0 / dt
    tempo_anterior = tempo_atual

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=10, minSize=(100, 100))

    elapsed_lib = tempo_atual - info_acesso["inicio_liberacao"] if info_acesso["inicio_liberacao"] > 0 else 999.0

    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        
        rosto_cortado = gray_frame[y:y+h, x:x+w]
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
        
        imagem_iluminada = aplicar_tan_triggs(resized)
        frame_para_enviar = imagem_iluminada

        pip_bgr = cv2.cvtColor(imagem_iluminada, cv2.COLOR_GRAY2BGR)
        pip_atual = cv2.resize(pip_bgr, (tamanho_pip, tamanho_pip))

        if elapsed_lib < TEMPO_MOVIMENTO_SERVO:
            cor = (0, 200, 255)
            texto_status = "ANALISANDO (ABRINDO)..."
        elif elapsed_lib < duracao_aberta:
            cor = (100, 220, 50)
            texto_status = "AUTORIZADO"
        elif elapsed_lib < duracao_total_ciclo:
            cor = (0, 215, 255)
            texto_status = "TRANCANDO (COOLDOWN)"
        elif info_acesso["estado"] == "NEGADO":
            cor = (0, 0, 255)
            texto_status = "BLOQUEADO"
        else:
            cor = (255, 150, 0)
            conf = info_acesso["confirmacoes_atuais"]
            texto_status = f"ANALISANDO ({conf}/{CONFIRMACOES_NECESSARIAS})"
            
        cv2.rectangle(frame, (x, y), (x+w, y+h), cor, 2)
        cv2.putText(frame, texto_status, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2)
        cv2.putText(frame, f"{info_acesso['nome'].upper()} ({info_acesso['distancia']:.1f})", (x, y+h+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2)
        
    else:
        frame_para_enviar = None
        pip_atual = np.zeros((tamanho_pip, tamanho_pip, 3), dtype=np.uint8)
        cv2.putText(pip_atual, "SEM ROSTO", (25, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # HUD PIP
    H, W = frame.shape[:2]
    x_pip = W - tamanho_pip - 20
    y_pip = 20
    frame[y_pip:y_pip+tamanho_pip, x_pip:x_pip+tamanho_pip] = pip_atual
    cv2.rectangle(frame, (x_pip, y_pip), (x_pip+tamanho_pip, y_pip+tamanho_pip), (255, 255, 255), 1)
    cv2.putText(frame, "VISAO ESP32", (x_pip, y_pip - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    # Textos globais de sistema
    data_hora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(frame, "CONTROLE DE ACESSO", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 220, 50), 2)
    cv2.putText(frame, f"DATA: {data_hora_str}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 220, 50), 1)
    cv2.putText(frame, f"FPS: {int(fps)}", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 220, 50), 1)

    cv2.imshow("Monitoramento de Acesso UERGS", frame)

    if cv2.waitKey(30) & 0xFF == ord('q'):
        rodando = False
        break

cap.release()
esp_serial.close()
cv2.destroyAllWindows()
thread_esp.join()