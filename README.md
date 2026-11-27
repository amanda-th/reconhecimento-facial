# Controle de Acesso: Sistema Híbrido de Reconhecimento Facial

<p align="center">
  <img src="https://img.shields.io/badge/C-A8B9CC?style=flat-square&logo=c&logoColor=black" alt="C" />
  <img src="https://img.shields.io/badge/C++-00599C?style=flat-square&logo=cplusplus&logoColor=white" alt="C++" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/Hardware-ESP32-E7352C?style=flat-square&logo=espressif&logoColor=white" alt="ESP32" />
</p>

**Controle de acesso por reconhecimento facial com processamento na borda (ESP32 + Python)**

Projeto desenvolvido para as disciplinas de Processamento de Imagens e Sistemas de Tempo Real.

**Linguagens:** C/C++ (firmware das duas ESP32, via Arduino IDE) e Python (captura, pré-processamento e geração do banco de rostos).

---

## Sumário

1. [Resumo](#1-resumo)
2. [Objetivos](#2-objetivos)
3. [Visão geral da arquitetura](#3-visão-geral-da-arquitetura)
4. [Fundamentação teórica](#4-fundamentação-teórica)
5. [Desenvolvimento: linha do tempo do projeto](#5-desenvolvimento-linha-do-tempo-do-projeto)
6. [Hardware e esquema elétrico](#6-hardware-e-esquema-elétrico)
7. [Estrutura do repositório](#7-estrutura-do-repositório)
8. [Como reproduzir o projeto](#8-como-reproduzir-o-projeto)
9. [Auditoria de acessos](#9-auditoria-de-acessos)
10. [Limitações conhecidas e trabalhos futuros](#10-limitações-conhecidas-e-trabalhos-futuros)
11. [Considerações finais](#11-considerações-finais)

---

## 1. Resumo

Este trabalho implementa um sistema de controle de acesso por reconhecimento facial em que a decisão de liberar ou não a porta é tomada dentro de um microcontrolador, e não em um computador ou serviço na nuvem. O PC fica responsável apenas por capturar a imagem, localizar o rosto e normalizar a iluminação. A partir daí, uma ESP32 extrai as características da imagem (MB-LBP), compara com um banco de rostos guardado na memória Flash e envia o resultado, por ESP-NOW, para uma segunda ESP32 que controla um servomotor e dois LEDs em uma maquete de porta.

O projeto uniu duas disciplinas: Processamento de Imagens (filtros, extração de características, classificação) e Sistemas de Tempo Real (tarefas em paralelo no FreeRTOS, comunicação sem fio, máquina de estados e tratamento de concorrência no atuador). O hardware é simples, e a maior parte do esforço foi dedicada ao processamento de imagens, área nova para mim, em que a primeira abordagem não funcionou e precisou ser trocada. Como boa parte do que está documentado aqui veio de coisas que deram errado, o histórico de desenvolvimento ocupa um espaço grande neste documento.

## 2. Objetivos

- Reconhecer rostos de forma que o resultado seja repetível e razoavelmente estável diante de mudanças de iluminação, sem depender de bibliotecas de IA prontas.
- Executar a parte pesada do reconhecimento (extração de características e classificação) na ESP32.
- Transmitir o resultado entre as placas sem depender de roteador Wi-Fi.
- Acionar uma tranca física de forma previsível, sem tremores no servo e sem reinicializações por queda de tensão.
- Manter um registro das tentativas de acesso.

## 3. Visão geral da arquitetura

O sistema tem três blocos:

```
 Câmera + PC (Python)            ESP32 Principal                  ESP32 Atuadora
 ---------------------           ------------------------         -------------------------
 Captura de vídeo                Recebe 64x64 via Serial          Recebe o pacote ESP-NOW
 Haar Cascade (acha rosto)  -->  Imagem integral             -->  Debounce (3 confirmações)
 Recorte + resize 64x64          MB-LBP + histograma 5x5          Servo (GPIO 18)
 Tan & Triggs                    Distância euclidiana             LEDs verde/vermelho
 HUD, PiP e log em CSV           Decisão (limiar)                 Cooldown e tempo de porta aberta
(USB / Serial 115200)            (ESP-NOW, MAC a MAC)
```

1. **PC (Python).** Atua como o "olho" do sistema. Captura o vídeo, localiza o rosto com Haar Cascade, recorta, redimensiona para 64x64, aplica o filtro de Tan & Triggs e envia os 4096 bytes da imagem pela porta Serial. Também desenha a interface (HUD) e grava o log de acessos.
2. **ESP32 Principal (C++).** Recebe a imagem, calcula o MB-LBP e o histograma, compara com os centroides gravados em `banco_rostos.h` usando distância euclidiana e envia o veredito (um `bool`) por ESP-NOW. Também devolve ao PC uma linha de texto com o nome e a distância, que é usada na interface.
3. **ESP32 Atuadora (C++).** Fica na maquete da porta. Recebe os pacotes, decide quando abrir e fechar a tranca e controla os LEDs através de uma Máquina de Estados não-bloqueante.

Esse arranjo segue a ideia de computação de borda: o PC é só um nó de aquisição e a decisão de segurança acontece no hardware que de fato aciona a tranca.

## 4. Fundamentação teórica

### 4.1 Processamento de Imagens

**Normalização de iluminação (Tan & Triggs).** A iluminação é o principal inimigo do reconhecimento facial, porque a mesma pessoa pode gerar imagens muito diferentes dependendo da luz da sala. O pré-processamento de Tan & Triggs, implementado em `aplicar_tan_triggs()`, tem três etapas: correção gama (γ = 0,2), diferença de gaussianas (DoG, com σ = 1,0 e σ = 2,0) e equalização de contraste local com CLAHE (`clipLimit = 2.0`, grade 8x8).

**MB-LBP (Multi-Block Local Binary Pattern).** O LBP clássico compara um pixel com seus 8 vizinhos. Na versão multi-bloco, a comparação é feita entre somas de blocos de pixels (aqui, blocos de 3x3). Para cada posição, a soma do bloco central é comparada com a dos 8 blocos ao redor, e o resultado vira um código de 8 bits. O que se obtém é uma descrição de textura, menos sensível a pequenas mudanças de expressão do que a comparação direta de pixels.

**Imagem integral.** Para calcular as somas de bloco sem percorrer todos os pixels toda vez, constrói-se uma imagem integral. Com ela, a soma de qualquer retângulo sai com apenas quatro acessos à memória, independentemente do tamanho do bloco. Isso foi o que tornou viável rodar o MB-LBP na ESP32.

**Histogramas por região.** A imagem de códigos LBP é dividida em uma grade 5x5. Cada uma das 25 regiões gera um histograma de 256 posições, e a concatenação resulta em um vetor de 6400 valores por rosto.

**Classificação.** Cada pessoa cadastrada é representada por um centroide, que é a média dos vetores de todas as suas fotos. A identificação consiste em calcular a distância euclidiana entre o vetor do rosto capturado e cada centroide, escolher o menor valor e compará-lo com um limiar (100,0 no código atual). Se a menor distância estiver abaixo do limiar, o acesso é liberado.

### 4.2 Sistemas de Tempo Real

**Paralelismo com FreeRTOS.** A ESP32 Principal usa os dois núcleos. No Core 0 roda uma tarefa que só lê a Serial (`receiveSerialTask`). No Core 1 roda a tarefa de processamento (`processImageTask`), que fica bloqueada até ser notificada (`xTaskNotifyGive` / `ulTaskNotifyTake`) de que uma imagem completa chegou. Assim, a leitura de I/O não disputa tempo com a parte matemática.

**Comunicação por ESP-NOW.** As placas conversam direto pelo endereço MAC, sem passar por roteador, o que elimina a variação de atraso de uma rede Wi-Fi comum. O pacote enviado é uma estrutura de um único `bool`.

**Máquina de estados não-bloqueante na atuadora.** O acionamento mecânico foi arquitetado como uma FSM (*Finite State Machine*) orientada a eventos. O callback do rádio atua estritamente sinalizando flags. O `loop()` monitora essas flags e gerencia o tempo de porta aberta (5s) e de cooldown (1,5s) de forma assíncrona usando `millis()`. Com isso, a espera física do servo não exige comandos `delay()`, garantindo que o processador nunca bloqueie e o rádio Wi-Fi nunca perca pacotes de reconhecimento durante o giro do motor.

## 5. Desenvolvimento: linha do tempo do projeto

O sistema não saiu pronto. Foram cinco fases, cada uma motivada por um problema da anterior. Os arquivos de cada fase foram mantidos no repositório como registro do processo.

### Fase 1: Detecção de bordas com Sobel

**Arquivos:** `gerar_rosto.py`, `gerar_banco.py`

A primeira ideia foi a mais direta: capturar o rosto no PC, aplicar a convolução de Sobel, redimensionar para 64x64 e enviar a matriz para a ESP32 comparar pixel a pixel com rostos guardados. O `gerar_rosto.py` gera um único rosto de referência e o `gerar_banco.py` evoluiu isso para um banco com vários rostos.

**Resultado.** Não funcionou bem. O mapa de bordas muda muito com a iluminação da sala e com qualquer pequena rotação do rosto, então a comparação direta de pixels gerava falsos positivos e falsos negativos o tempo todo.

### Fase 2: Tan & Triggs e MB-LBP

**Arquivos:** `capturar_minhas_fotos.py`, `gerar_banco_turma.py`, `processar_banco_antigo.py`

A mudança de abordagem foi parar de comparar pixels e passar a comparar características. O Python ficou com a tarefa de estabilizar a imagem, e a ESP32 passou a calcular o MB-LBP e os histogramas. Um detalhe de projeto importante: o banco de rostos é gerado offline pelo Python, mas o código que extrai o MB-LBP em Python (`extrair_lbph()`) reproduz exatamente a lógica do C++, usando imagem integral. 

O segundo desafio foi o banco de dados. A turma já tinha um conjunto de fotos antigas que precisou ser processado em lote pelo script `processar_banco_antigo.py`.

### Fase 3: Unificação do fluxo de cadastro

**Arquivo final:** `cadastrar_pessoa.py`

Para não precisar rodar vários scripts, juntei o fluxo de cadastro e processamento. O script abre uma janela pedindo o nome, captura as fotos pela webcam, recalcula o banco inteiro a partir da pasta e escreve o `banco_rostos.h` direto no diretório da ESP32. O caminho de compilação foi automatizado independentemente do Sistema Operacional.

### Fase 4: Desafios de integração hardware-software (Jitter, Brownout e EMI)

**Arquivo final:** `esp-secundaria.ino`

Com o reconhecimento estável, a rodagem contínua do sistema expôs fenômenos físicos de campo:

1. **Jitter mecânico por EMI (Interferência Eletromagnética):** Mesmo com o motor parado e após o comando de `detach()`, o servo apresentava espasmos aleatórios. **Causa:** O pino de sinal, em estado de alta impedância (flutuando), atuava como uma antena de rádio e captava o ruído de RF das rajadas do ESP-NOW.
2. **Brownout (Queda de Tensão):** O arranque mecânico exigia um pico de corrente abrupto (*inrush current*), derrubando a tensão da placa e disparando reinicializações de proteção.

**Correções híbridas aplicadas:**
- O servo passou a ser alimentado direto pela linha de 5V (VIN), separando-o do regulador de 3.3V.
- **Aterramento Lógico (Software):** Logo após desligar o PWM (`detach()`), o pino de controle foi forçado como `OUTPUT` e `LOW`. Esse aterramento de sinal silenciou a interferência de rádio.
- **Filtro de Desacoplamento (Hardware):** A tensão elétrica foi blindada implementando um banco em paralelo de **3 capacitores eletrolíticos de 100 µF** nas trilhas de alimentação, formando um reservatório equivalente de 300 µF. Esse banco forneceu a energia rápida necessária para o tranco do motor, achatando a curva de queda de tensão ($\Delta V$) na linha principal.

### Fase 5: Sincronia entre tela e porta, e condições de corrida

**Arquivos finais:** `cam.py`, `esp-secundaria.ino`

A interface e o mundo físico operavam em tempos diferentes. Soluções adotadas na FSM:
1. **Debounce:** A atuadora só abre depois de receber 3 pacotes "reconhecido" consecutivos, mitigando eventuais ruídos visuais da câmera.
2. **Memória de estado e Cooldown:** O sistema respeita o tempo da engrenagem. Após o fechamento, ignora a câmera por 1,5s. Sem esse *cooldown*, uma mudança súbita de identificação colidiria logicamente com as funções motoras, criando uma condição de corrida destrutiva.

## 6. Hardware e esquema elétrico

### 6.1 ESP32 Principal (processamento)

Conectada ao PC por USB, usada para a comunicação Serial. Não precisa de fiação externa.

### 6.2 ESP32 Secundária (atuador)

O servomotor e a estabilização elétrica são montados na mesma barramento da protoboard.

| Componente | Pino da ESP32 (GPIO) | Conexão |
| ----- | ----- | ----- |
| Servomotor (sinal) | 18 | Fio de sinal (amarelo/laranja) |
| LED verde | 19 | Perna longa (+), com resistor |
| LED vermelho | 21 | Perna longa (+), com resistor |
| GND comum | GND | Fio do servo, perna (-) dos LEDs e perna curta (-) dos capacitores |
| Alimentação do servo | VIN / 5V | Fio vermelho do servo e perna longa (+) dos capacitores |
| Banco de Filtro | Paralelo ao 5V e GND | 3x Capacitores eletrolíticos de 100 µF |

Os LEDs precisam de resistores de 220 Ω ou 330 Ω em série.

### 6.3 Consumo de memória do banco

Cada pessoa cadastrada ocupa 6400 valores `double` (cerca de 50 KB) na Flash. Por isso o firmware principal precisa ser gravado com a partição **Huge APP**.

## 7. Estrutura do repositório

| Arquivo | Função | Situação |
| ----- | ----- | ----- |
| `esp-main.ino` | Firmware da ESP32 Principal (MB-LBP, distância, ESP-NOW) | Atual |
| `esp-secundaria.ino` | Firmware da ESP32 Atuadora (servo, LEDs, FSM, debounce) | Atual |
| `cam.py` | Reconhecimento em tempo real, HUD, PiP e log CSV | Atual |
| `cadastrar_pessoa.py` | Captura de fotos e geração do `banco_rostos.h` | Atual |
| `capturar_minhas_fotos.py` | Captura de fotos (cadastro em etapa separada) | Fase 2 |
| `processar_banco_antigo.py` | Processamento em lote das fotos antigas da turma | Fase 2 |
| `gerar_banco_turma.py` | Geração do banco a partir de `imagens_processadas/` | Fase 2 |

**Nota de Privacidade:** As pastas `imagens/` e `imagens_processadas/` (que contém as capturas biométricas da turma) foram isoladas no arquivo `.gitignore` e removidas por via de reescrita da árvore histórica de commits para proteger o banco de dados pessoal, sendo mantidas estritamente no armazenamento local.

## 8. Como reproduzir o projeto

### 8.1 Pré-requisitos

- Arduino IDE com suporte a placas ESP32.
- Biblioteca `ESP32Servo` (instalar pelo Gerenciador de Bibliotecas).
- Python 3 com `opencv-python`, `pyserial` e `numpy`.

**Linux (Ubuntu / Linux Mint):**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk python3-opencv python3-serial
pip3 install numpy
```

**Windows:** (marcando "Add to PATH"):
```cmd
pip install opencv-python pyserial numpy
```

### 8.2 Gravando as placas

1. Conecte a **ESP32 Atuadora** e grave o `esp-secundaria.ino`.
2. Desconecte a atuadora e conecte a **ESP32 Principal**.
3. No `esp-main.ino`, atualize a variável `macESP2` com o MAC Address correto da placa atuadora.
4. Grave o `esp-main.ino` utilizando a aba Tools > Partition Scheme > **Huge APP**.
5. Feche o Monitor Serial para liberar a porta para o script Python.

### 8.3 Cadastrando pessoas

```bash
python3 cadastrar_pessoa.py
```
Pressione `c` para capturar as fotos e `q` para salvar. **Regrave a ESP32 Principal** após a geração automática do `banco_rostos.h`. O XML de reconhecimento do Haar Cascade deve estar na mesma raiz do script de execução.

### 8.4 Executando o reconhecimento

Ajuste a variável `SERIAL_PORT` no `cam.py`:
- Windows: `COM7` (ou a porta correspondente)
- Linux: `/dev/ttyUSB0` ou `/dev/ttyACM0` (garanta permissão de I/O rodando `sudo chmod a+rw /dev/ttyUSB0`).

```bash
python3 cam.py
```

## 9. Auditoria de acessos

Cada tentativa de acesso é registrada em `relatorio_acessos.csv`, com as colunas `Data_Hora`, `Nome`, `Status` e `Distancia_LBP`. A interface mostra o *bounding box* dinâmico colorido conforme os estados da máquina (processando, autorizado, bloqueado), indicando via terminal o quadro de inferência reduzido para 64x64 recebido pelo microcontrolador.

## 10. Limitações conhecidas e trabalhos futuros

- **Limiar fixo.** O valor de 100,0 foi ajustado empiricamente depois da troca de algoritmo e não passou por uma avaliação sistemática (taxas de falso positivo e falso negativo). Um próximo passo natural seria coletar um conjunto de teste e traçar essas curvas para escolher o limiar com critério.
- **Sem detecção de vivacidade.** O sistema não distingue um rosto real de uma foto exibida na câmera. Para um uso real de segurança isso seria obrigatório.
- **ESP-NOW sem criptografia.** O par é configurado com `encrypt = false`. Qualquer dispositivo que conheça o MAC da atuadora poderia, em tese, enviar pacotes de liberação.
- **Latência não medida.** A comunicação por ESP-NOW é, em geral, de baixa latência, mas não fiz uma medição formal do tempo entre a captura da imagem e o acionamento da porta.
- **Banco embutido no firmware.** Cada novo cadastro exige regravar a ESP32 Principal. Guardar o banco em um sistema de arquivos (SPIFFS/LittleFS) permitiria atualizá-lo sem recompilar.
- **Somente o primeiro rosto.** Se houver mais de uma pessoa em quadro, apenas o primeiro rosto detectado é processado.

## 11. Considerações finais

A parte mais difícil do projeto foi o processamento de imagens. O hardware é simples: uma ESP32 que não tem nada ligado além do cabo USB e outra com um servomotor e dois LEDs. Eu já tinha alguma experiência com ESP32, então os problemas físicos, como a alimentação do motor e o conflito com o rádio, deram trabalho, mas eram problemas que eu sabia por onde começar a investigar.

Já o reconhecimento facial era território novo. Foi a primeira vez que trabalhei com processamento de imagens dessa forma, e boa parte do tempo foi gasta entendendo por que a primeira versão, com Sobel, não funcionava e o que precisava mudar. A principal lição foi que a representação da imagem importa mais do que a comparação feita depois dela: com o mesmo tipo de classificador, a troca de bordas brutas por uma imagem normalizada (Tan & Triggs) e descrita por textura (MB-LBP com histogramas por região) foi o que fez o sistema passar a funcionar. Também aprendi, na prática, por que a imagem integral é necessária para rodar esse tipo de algoritmo em um microcontrolador, e a importância de manter o código do Python e o do C++ calculando exatamente a mesma coisa.

A parte de Sistemas de Tempo Real veio como complemento a isso. Tarefas separadas por núcleo, debounce, cooldown e uma máquina de estados deixaram de ser conceito de aula quando o servo começou a tremer e a placa a reiniciar. Foram problemas menores em complexidade, mas serviram para ver, no equipamento ligado, o que acontece quando eventos chegam quase ao mesmo tempo.

O repositório mantém os scripts das fases anteriores de propósito, porque o caminho até a versão atual faz parte do trabalho.
