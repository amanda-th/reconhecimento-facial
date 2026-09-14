# Sistema de aquisição Câmera + Memória

# NECESSÁRIO: pip install opencv-python pyserial
import cv2
import serial
import time
import sys

# Configurações do Sistema
SERIAL_PORT = '/dev/ttyUSB0'  # Altere para /dev/ttyACM0 ou COM3 se necessário
BAUD_RATE = 115200          # Taxa de transmissão de dados (deve ser igual na ESP32)
WIDTH = 64
HEIGHT = 64

# 1. Inicializa a porta Serial
try:
    esp_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    print(f"Sucesso: Conectado a {SERIAL_PORT}")
except Exception as e:
    print(f"Erro ao abrir a porta serial. Verifique a conexão e as permissões.\n{e}")
    sys.exit()

# Dá um tempo para a ESP32 reiniciar (comportamento padrão ao abrir a porta serial)
time.sleep(2)

# 2. Inicializa a Webcam (0 costuma ser a webcam integrada)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Erro: Não foi possível abrir a câmera.")
    sys.exit()

print("Iniciando captura e envio... Pressione 'q' na janela de vídeo para encerrar.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Erro ao ler o frame da câmera.")
        break

    # 3. Pré-processamento
    # Converte para tons de cinza (matriz 2D de 8 bits por pixel)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Redimensiona para 64x64 pixels
    resized = cv2.resize(gray, (WIDTH, HEIGHT))

    # Mostra na tela do PC o que a ESP32 está "vendo"
    cv2.imshow("Visão do Sistema de Aquisição", resized)

    # 4. Preparação dos Dados
    # Achata a matriz 2D (64x64) em um array 1D de 4096 bytes
    image_bytes = resized.flatten().tobytes()

    # 5. Comunicação e Handshake (Controle de Fluxo)
    # Enviamos um marcador de início (o caractere 'S' de Start)
    # Isso impede que a ESP32 comece a ler os dados no meio de um frame
    esp_serial.write(b'S') 
    
    # Envia o pacote de imagem
    esp_serial.write(image_bytes)
    
    # Espera a ESP32 processar o Sobel e responder antes de mandar o próximo frame.
    # Sem isso, o PC enviaria dados mais rápido do que a ESP32 consegue processar, estourando o buffer.
    resposta = esp_serial.readline().decode('utf-8').strip()
    
    if resposta:
        print(f"ESP32 respondeu: {resposta}")

    # Condição de saída
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Limpeza e encerramento
cap.release()
esp_serial.close()
cv2.destroyAllWindows()
print("Sistema encerrado.")