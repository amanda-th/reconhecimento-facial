import cv2
import os
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
# CONFIGURAÇÕES DE DIRETÓRIOS E CASCADE
# =========================================================================
pasta_origem = 'imagens'
pasta_destino = 'imagens_processadas'

# Cria a pasta de destino se não existir
if not os.path.exists(pasta_destino):
    os.makedirs(pasta_destino)

# Carrega a IA de detecção do OpenCV
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

WIDTH = 64
HEIGHT = 64
rostos_processados = 0
rostos_nao_encontrados = []

print(f"Iniciando varredura na pasta '{pasta_origem}'...\n")

# =========================================================================
# PROCESSAMENTO EM LOTE (BATCH PROCESSING)
# =========================================================================
for nome_arquivo in os.listdir(pasta_origem):
    # Filtra apenas arquivos de imagem
    if not nome_arquivo.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
        continue
        
    caminho_completo = os.path.join(pasta_origem, nome_arquivo)
    imagem_original = cv2.imread(caminho_completo)
    
    if imagem_original is None:
        print(f"Erro ao ler a imagem: {nome_arquivo}")
        continue

    # Converte para tons de cinza para a detecção
    gray = cv2.cvtColor(imagem_original, cv2.COLOR_BGR2GRAY)
    
    # Busca o rosto na imagem original
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30))

    if len(faces) > 0:
        # Pega o primeiro rosto encontrado
        (x, y, w, h) = faces[0]
        
        # 1. Recorta o rosto
        rosto_cortado = gray[y:y+h, x:x+w]
        
        # 2. Padroniza o tamanho para 64x64
        resized = cv2.resize(rosto_cortado, (WIDTH, HEIGHT))
        
        # 3. Aplica o filtro de iluminação
        rosto_final = aplicar_tan_triggs(resized)
        
        # Salva na nova pasta
        caminho_salvar = os.path.join(pasta_destino, nome_arquivo)
        cv2.imwrite(caminho_salvar, rosto_final)
        
        print(f"[OK] Processado: {nome_arquivo}")
        rostos_processados += 1
    else:
        # Se a foto do colega for muito ruim ou distante e o cascade falhar
        print(f"[FALHA] Nenhum rosto detectado em: {nome_arquivo}")
        rostos_nao_encontrados.append(nome_arquivo)

print("\n=======================================================")
print(f"Processamento concluído! {rostos_processados} rostos convertidos com sucesso.")
if rostos_nao_encontrados:
    print(f"Atenção: O algoritmo não encontrou rostos nestas fotos: {rostos_nao_encontrados}")
print(f"As imagens prontas para a ESP32 estão na pasta '{pasta_destino}'.")