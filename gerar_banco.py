import cv2
import numpy as np

WIDTH = 64
HEIGHT = 64

Gx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
Gy = np.array([[ 1, 2, 1], [ 0, 0, 0], [-1,-2,-1]])

def aplicar_sobel_manual(imagem):
    output = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            somaX = 0
            somaY = 0
            for i in range(3):
                for j in range(3):
                    pixel = int(imagem[y + i - 1, x + j - 1])
                    somaX += pixel * Gx[i, j]
                    somaY += pixel * Gy[i, j]
            
            magnitude = int(np.sqrt((somaX ** 2) + (somaY ** 2)))
            if magnitude > 255: magnitude = 255
            output[y, x] = magnitude
    return output

cap = cv2.VideoCapture(0)
rostos = {}

print("Comandos:")
print("[1] Capturar Rosto Neutro")
print("[2] Capturar Sem Óculos")
print("[3] Capturar Rosto de Perto")
print("[s] Salvar banco de dados e sair")

while True:
    ret, frame = cap.read()
    if not ret: break
        
    cv2.putText(frame, "1:Neutro | 2:Sem Oculos | 3:Perto | S:Salvar", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    cv2.imshow("Gerador de Banco de Dados", frame)
    key = cv2.waitKey(1) & 0xFF
    
    if key in [ord('1'), ord('2'), ord('3')]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (WIDTH, HEIGHT))
        sobel_img = aplicar_sobel_manual(resized)
        
        if key == ord('1'):
            rostos['rosto_Neutro'] = sobel_img
            print("-> Rosto Neutro capturado!")
        elif key == ord('2'):
            rostos['rosto_SemOculos'] = sobel_img
            print("-> Rosto Sem Óculos capturado!")
        elif key == ord('3'):
            rostos['rosto_Perto'] = sobel_img
            print("-> Rosto Perto capturado!")
            
    elif key == ord('s'):
        if len(rostos) == 3:
            print("Gerando banco de dados em C++...")
            with open("banco_rostos.txt", "w") as f:
                for nome, img in rostos.items():
                    f.write(f"uint8_t {nome}[HEIGHT][WIDTH] = {{\n")
                    for y in range(HEIGHT):
                        f.write("    {")
                        f.write(", ".join(str(p) for p in img[y]))
                        f.write("},\n" if y < HEIGHT - 1 else "}\n")
                    f.write("};\n\n")
            print("Sucesso! Arquivo 'banco_rostos.txt' criado.")
            break
        else:
            print(f"Erro: Você capturou apenas {len(rostos)} de 3 rostos. Capture os que faltam!")

cap.release()
cv2.destroyAllWindows()