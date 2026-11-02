import cv2
import serial
import time
import sys
import threading

SERIAL_PORT = 'COM7' 
BAUD_RATE = 115200
WIDTH = 64
HEIGHT = 64

frame_para_enviar = None
rodando = True

try:
    esp_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5)
    print(f"Sucesso: Conectado a {SERIAL_PORT}")
except Exception as e:
    print(f"Erro ao abrir a porta serial.\n{e}")
    sys.exit()

time.sleep(2)

# =========================================================================
# THREAD SECUNDÁRIA: Comunicação com a ESP32
# =========================================================================
def thread_comunicacao_esp():
    global frame_para_enviar, rodando
    while rodando:
        if frame_para_enviar is not None:
            frame_atual = frame_para_enviar.copy()
            image_bytes = frame_atual.flatten().tobytes()
            
            esp_serial.write(b'S')
            esp_serial.write(image_bytes)
            
            resposta = esp_serial.readline().decode('utf-8', errors='ignore').strip()
            if resposta:
                print(f"ESP32 respondeu: {resposta}")
                if "ACESSO" in resposta:
                    _ = esp_serial.readline().decode('utf-8', errors='ignore').strip()
        else:
            time.sleep(0.1)

thread_esp = threading.Thread(target=thread_comunicacao_esp)
thread_esp.start()

# =========================================================================
# THREAD PRINCIPAL: Rastreamento Facial Inteligente (Haar Cascade)
# =========================================================================
# Carrega o modelo pré-treinado do OpenCV para faces frontais
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)

print("Sistema iniciado com Rastreamento Dinâmico. Pressione 'q' para sair.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Detecta rostos na imagem em tempo real, ajustando a escala automaticamente
    faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))

    # Se detectar pelo menos um rosto, processa o primeiro
    if len(faces) > 0:
        (x, y, w, h) = faces[0]
        
        # Recorta estritamente a região do rosto rastreado
        rosto_cortado = gray_frame[y:y+h, x:x+w]
        
        # Redimensiona a área detectada para o padrão rígido da ESP32
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        
        # Atualiza a matriz que será enviada via Serial
        frame_para_enviar = resized

        # Desenha o quadrado verde acompanhando o movimento
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow("O que a ESP32 enxerga (Normalizado)", resized)
    else:
        # Se você sair do quadro, bloqueia o envio de ruído para a placa
        frame_para_enviar = None

    cv2.imshow("Visao Geral com Rastreamento", frame)

    if cv2.waitKey(30) & 0xFF == ord('q'):
        rodando = False
        break

cap.release()
esp_serial.close()
cv2.destroyAllWindows()
thread_esp.join()