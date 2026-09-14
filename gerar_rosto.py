import cv2
import numpy as np

WIDTH = 64
HEIGHT = 64

# Kernels de Sobel idênticos ao do código em C++
Gx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
Gy = np.array([[ 1, 2, 1], [ 0, 0, 0], [-1,-2,-1]])

def aplicar_sobel_manual(imagem):
    """
    Aplica o Sobel com a mesma lógica do C++ para garantir 
    que os valores da matriz sejam 100% idênticos.
    """
    output = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            somaX = 0
            somaY = 0
            
            # Convolução
            for i in range(3):
                for j in range(3):
                    pixel = int(imagem[y + i - 1, x + j - 1])
                    somaX += pixel * Gx[i, j]
                    somaY += pixel * Gy[i, j]
            
            magnitude = int(np.sqrt((somaX ** 2) + (somaY ** 2)))
            
            # Normalização (truncamento)
            if magnitude > 255: magnitude = 255
            
            output[y, x] = magnitude
            
    return output

# 1. Inicializa a câmera
cap = cv2.VideoCapture(0)

print("Posicione seu rosto na câmera.")
print("Pressione 's' para salvar o rosto ideal ou 'q' para sair.")

while True:
    ret, frame = cap.read()
    if not ret:
        break
        
    # Mostra a imagem normal para você se posicionar
    cv2.imshow("Captura do Rosto Ideal", frame)
    
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('s'):
        # 2. Processa a imagem
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (WIDTH, HEIGHT))
        
        print("\nProcessando o filtro de Sobel... Aguarde.")
        sobel_img = aplicar_sobel_manual(resized)
        
        # 3. Gera o código em C++
        print("Gerando o arquivo matriz_rosto.txt...")
        with open("matriz_rosto.txt", "w") as f:
            f.write("uint8_t rostoIdeal[HEIGHT][WIDTH] = {\n")
            for y in range(HEIGHT):
                f.write("    {")
                linha = ", ".join(str(pixel) for pixel in sobel_img[y])
                f.write(linha)
                f.write("},\n" if y < HEIGHT - 1 else "}\n")
            f.write("};\n")
            
        print("Sucesso! Arquivo 'matriz_rosto.txt' criado.")
        
        # Mostra o resultado do Sobel para você ver como a ESP32 te enxerga
        cv2.imshow("Visão do Sobel (ESP32)", sobel_img)
        cv2.waitKey(3000) # Mostra por 3 segundos
        break
        
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()