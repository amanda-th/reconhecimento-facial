import cv2
import os

# Adicionando as constantes que faltavam para o redimensionamento
WIDTH = 64
HEIGHT = 64

# Garante que vai salvar na mesma pasta da turma
pasta = 'imagens'
if not os.path.exists(pasta):
    os.makedirs(pasta)

cap = cv2.VideoCapture(0)
print("Pressione 'c' para capturar uma foto sua. Tire cerca de 5 fotos.")
print("Pressione 'q' para sair.")

contador = 1
while True:
    ret, frame = cap.read()
    if not ret:
        print("Erro ao ler o frame da câmera.")
        break

    # Pega as dimensões reais da sua webcam
    h, w = frame.shape[:2]
    
    # Define o tamanho do "centrinho"
    tamanho_quadrado = 300
    
    # Calcula as coordenadas para cortar o meio da imagem
    y_inicio = (h - tamanho_quadrado) // 2
    y_fim = y_inicio + tamanho_quadrado
    x_inicio = (w - tamanho_quadrado) // 2
    x_fim = x_inicio + tamanho_quadrado
    
    # Corta fora as bordas da imagem original
    frame_cortado = frame[y_inicio:y_fim, x_inicio:x_fim]

    # Converte APENAS O ROSTO para cinza e reduz
    gray = cv2.cvtColor(frame_cortado, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (WIDTH, HEIGHT))

    # Mostra a imagem com o quadrado verde e a visão da ESP32
    cv2.rectangle(frame, (x_inicio, y_inicio), (x_fim, y_fim), (0, 255, 0), 2)
    cv2.imshow("Visao Geral (Verde = Area Processada)", frame)
    cv2.imshow("O que a ESP32 enxerga (64x64)", resized)

    # Lógica de captura e salvamento de imagem
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('c'):
        # Salva o frame_cortado (sem o fundo da sua casa) para evitar o erro do cenário!
        nome_arquivo = os.path.join(pasta, f"amanda_{contador}.jpg")
        cv2.imwrite(nome_arquivo, frame_cortado)
        print(f"Sucesso! Foto salva: {nome_arquivo}")
        contador += 1
        
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()