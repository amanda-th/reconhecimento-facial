import cv2
import os

# Garante que vai salvar na mesma pasta da turma
pasta = 'imagens'
if not os.path.exists(pasta):
    os.makedirs(pasta)

cap = cv2.VideoCapture(0)
print("Pressione 'c' para capturar uma foto sua. Tire cerca de 5 fotos (mude levemente a expressao/distancia).")
print("Pressione 'q' para sair.")

contador = 1
while True:
    ret, frame = cap.read()
    if not ret:
        break
        
    cv2.imshow("Adicionando ao Banco de Dados", frame)
    key = cv2.waitKey(1) & 0xFF
    
    if key == ord('c'):
        # Salva a imagem com o seu nome para o algoritmo K-means agrupar depois
        nome_arquivo = os.path.join(pasta, f"amanda_{contador}.jpg")
        cv2.imwrite(nome_arquivo, frame)
        print(f"Sucesso! Foto salva: {nome_arquivo}")
        contador += 1
        
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()