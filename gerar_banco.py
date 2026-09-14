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
rostos = [] # Agora é uma lista, pode crescer o quanto você quiser!

print("Comandos:")
print("[Espaço] Capturar um novo rosto para o banco")
print("[s] Salvar banco_rostos.h e sair")

while True:
    ret, frame = cap.read()
    if not ret: break
        
    cv2.putText(frame, f"Rostos salvos: {len(rostos)} | Espaco: Capturar | S: Salvar", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    cv2.imshow("Gerador de Banco de Dados", frame)
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord(' '): # Tecla Espaço
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (WIDTH, HEIGHT))
        sobel_img = aplicar_sobel_manual(resized)
        
        rostos.append(sobel_img)
        print(f"-> Rosto {len(rostos)} capturado!")
            
    elif key == ord('s'):
        if len(rostos) > 0:
            print("Gerando banco_rostos.h...")
            with open("banco_rostos.h", "w") as f:
                f.write("#ifndef BANCO_ROSTOS_H\n#define BANCO_ROSTOS_H\n\n")
                f.write("#include <Arduino.h>\n\n")
                f.write(f"const int NUM_ROSTOS = {len(rostos)};\n\n")
                
                # O 'const' garante que isso vá para a Flash, salvando a RAM!
                f.write("const uint8_t banco_rostos[][64][64] = {\n")
                
                for idx, img in enumerate(rostos):
                    f.write("    {\n")
                    for y in range(HEIGHT):
                        f.write("        {")
                        f.write(", ".join(str(p) for p in img[y]))
                        f.write("},\n" if y < HEIGHT - 1 else "}\n")
                    f.write("    },\n" if idx < len(rostos) - 1 else "    }\n")
                
                f.write("};\n\n#endif\n")
            print("Sucesso! Arquivo 'banco_rostos.h' criado.")
            break
        else:
            print("Erro: Capture pelo menos 1 rosto antes de salvar.")

cap.release()
cv2.destroyAllWindows()