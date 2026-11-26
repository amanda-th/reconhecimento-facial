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

* Reconhecer rostos de forma que o resultado seja repetível e razoavelmente estável diante de mudanças de iluminação, sem depender de bibliotecas de IA prontas.
* Executar a parte pesada do reconhecimento (extração de características e classificação) na ESP32.
* Transmitir o resultado entre as placas sem depender de roteador Wi-Fi.
* Acionar uma tranca física de forma previsível, sem tremores no servo e sem reinicializações por queda de tensão.
* Manter um registro das tentativas de acesso.

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
3. **ESP32 Atuadora (C++).** Fica na maquete da porta. Recebe os pacotes, decide quando abrir e fechar a tranca e controla os LEDs.

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

**Máquina de estados na atuadora.** O comportamento da porta é descrito por estados (trancada, aberta, em cooldown) e controlado pelo relógio do sistema (`millis()`), não por esperas longas. O tempo de porta aberta (5 s) e o cooldown (1,5 s) são medidos dessa forma.

**Debounce e cooldown.** O debounce exige 3 pacotes "reconhecido" consecutivos antes de abrir a porta. O cooldown deixa o atuador ignorando a câmera por 1,5 s depois de fechar. Os dois mecanismos existem por causa de problemas reais, descritos na linha do tempo.

## 5. Desenvolvimento: linha do tempo do projeto

O sistema não saiu pronto. Foram cinco fases, cada uma motivada por um problema da anterior. Os arquivos de cada fase foram mantidos no repositório como registro do processo.

### Fase 1: Detecção de bordas com Sobel

**Arquivos:** `gerar_rosto.py`, `gerar_banco.py`

A primeira ideia foi a mais direta: capturar o rosto no PC, aplicar a convolução de Sobel (matrizes Gx e Gy, implementadas à mão para ficarem idênticas à versão em C++), redimensionar para 64x64 e enviar a matriz para a ESP32 comparar pixel a pixel com rostos guardados. O `gerar_rosto.py` gera um único rosto de referência (`matriz_rosto.txt`) e o `gerar_banco.py` evoluiu isso para um banco com vários rostos, escrito em `banco_rostos.h` como matrizes `uint8_t` de 64x64.

**Resultado.** Não funcionou bem. O mapa de bordas muda muito com a iluminação da sala e com qualquer pequena rotação do rosto, então a comparação direta de pixels gerava falsos positivos e falsos negativos o tempo todo. Além disso, essa versão usava a imagem inteira da câmera redimensionada, sem localizar o rosto antes, o que piorava ainda mais a variação entre capturas.

### Fase 2: Tan & Triggs e MB-LBP

**Arquivos:** `capturar_minhas_fotos.py`, `gerar_banco_turma.py`, `processar_banco_antigo.py`

A mudança de abordagem foi parar de comparar pixels e passar a comparar características. O Python ficou com a tarefa de estabilizar a imagem (localizar o rosto com Haar Cascade, recortar e aplicar Tan & Triggs), e a ESP32 passou a calcular o MB-LBP e os histogramas.

Um detalhe de projeto importante: o banco de rostos é gerado offline pelo Python, mas o código que extrai o MB-LBP em Python (`extrair_lbph()`) reproduz exatamente a lógica do C++, incluindo a mesma soma por imagem integral. Se os dois lados calculassem coisas diferentes, os vetores não seriam comparáveis.

O segundo desafio foi o banco de dados. A turma já tinha um conjunto de fotos antigas, em `.bmp` e com tamanhos variados. O `processar_banco_antigo.py` varre a pasta `imagens/`, detecta o rosto em cada arquivo, recorta, aplica Tan & Triggs e salva o resultado em `imagens_processadas/`. Depois, o `gerar_banco_turma.py` lê essa pasta, agrupa as fotos por pessoa (o nome é extraído do nome do arquivo), calcula o centroide de cada uma e escreve o `banco_rostos.h`. O `capturar_minhas_fotos.py` serve para cadastrar novas pessoas pela webcam.

Funcionava, mas o fluxo era manual: eram três scripts diferentes, rodados em ordem, e o `gerar_banco_turma.py` tinha o caminho da pasta da ESP32 fixo no código (um caminho de Windows específico da minha máquina).

### Fase 3: Unificação do fluxo de cadastro

**Arquivo final:** `cadastrar_pessoa.py`

Para não precisar rodar vários scripts toda vez que alguém novo fosse cadastrado, juntei tudo em um só. O script abre uma janela (`tkinter`) pedindo o nome, captura as fotos pela webcam (tecla `c`), e ao encerrar (tecla `q`) recalcula o banco inteiro a partir de `imagens_processadas/` e escreve o `banco_rostos.h` direto em `esp-main/`. O caminho é montado com `os.path.join`, então funciona igual no Windows e no Linux.

Aproveitei para corrigir um problema de nomes: como as fotos novas são salvas como `nome_1.jpg`, `nome_2.jpg`, a função `extrair_nome()` precisou passar a remover esse sufixo `_N`, senão a mesma pessoa poderia ser tratada como identidades diferentes.

Depois de gerar o banco é preciso regravar a ESP32 Principal, porque o banco fica compilado dentro do firmware.

### Fase 4: Problemas físicos (jitter, brownout e Wi-Fi)

**Arquivo final:** `esp-secundaria.ino`

Com o reconhecimento funcionando, a atenção passou para o lado físico. A montagem é simples, mas rodar o sistema de forma contínua expôs três problemas que eu não tinha visto nos testes isolados de cada placa:

1. **Servo tremendo (jitter).** Enquanto o rosto estivesse em quadro e o resultado fosse "negado", a câmera mandava um pacote para cada frame processado. A atuadora recebia dezenas de comandos de "trancar" por segundo e o servo ficava tremendo.
2. **Reinicializações (brownout).** O arranque do motor consome bastante corrente. Alimentando o servo pelo 3V3, a tensão caía e o detector de brownout da ESP32 reiniciava a placa.
3. **Interferência entre rádio e PWM.** Com o servo energizado e o ESP-NOW ativo, o servo dava movimentos espúrios mesmo parado. Minha hipótese, baseada no comportamento observado, é que a atividade do rádio interferia na geração do sinal PWM do servo.

**Correções aplicadas:**

* O servo passou a ser alimentado pelo pino VIN/5V.
* Criei a flag `servoJaEstaNoZero`, para a atuadora mandar o comando de trancar uma única vez, e não a cada pacote "negado".

### Fase 5: Sincronia entre tela e porta, e condições de corrida

**Arquivos finais:** `cam.py`, `esp-secundaria.ino`

Depois de estabilizar o motor, apareceu outro problema: a tela do computador mudava para "liberado" ou "negado" instantaneamente, mas a porta física leva tempo para abrir e a pessoa precisa passar. A interface e o mundo físico estavam em tempos diferentes.

Soluções adotadas:

1. **Debounce.** A atuadora só abre depois de receber 3 pacotes "reconhecido" consecutivos (`FOTOS_NECESSARIAS`). Um único frame bom no meio de ruído não abre a porta. O `cam.py` aplica a mesma regra de 3 confirmações para mostrar "AUTORIZADO".
2. **Memória de estado.** A porta fica aberta por 5 s (`TEMPO_PERMANENCIA`). O `cam.py` guarda o instante da liberação e mantém a tela em verde durante esses 5 s, ficando em sincronia com a porta.
3. **Cooldown.** Depois que a porta fecha, a atuadora ignora a câmera por 1,5 s (`TEMPO_COOLDOWN`). Sem isso, se alguém cobrisse o rosto no instante exato em que a porta estava fechando, chegava um comando de "negado" no meio do movimento do servo, e os dois comandos entravam em conflito (uma condição de corrida entre o fechamento por tempo e o comando vindo do rádio).
4. **Auditoria.** Acrescentei uma miniatura (Picture-in-Picture) mostrando a imagem que a ESP32 recebe e um registro em CSV das tentativas, com intervalo mínimo de 3 s entre registros para não encher o arquivo.

## 6. Hardware e esquema elétrico

### 6.1 ESP32 Principal (processamento)

Conectada ao PC por USB, usada para a comunicação Serial. Não precisa de fiação externa.

### 6.2 ESP32 Secundária (atuador)

O servomotor deve ser alimentado pelo pino **VIN/5V**. Ligar o servo no 3V3 provoca queda de tensão e reinicialização da placa (ver Fase 4).

| Componente | Pino da ESP32 (GPIO) | Conexão |
| ----- | ----- | ----- |
| Servomotor (sinal) | 18 | Fio de sinal (amarelo/laranja) |
| LED verde | 19 | Perna longa (+), com resistor |
| LED vermelho | 21 | Perna longa (+), com resistor |
| GND comum | GND | Fio marrom/preto do servo e perna (-) dos LEDs |
| Alimentação do servo | VIN ou 5V | Fio vermelho do servo |

Os LEDs precisam de resistores de 220 Ω ou 330 Ω em série.

### 6.3 Consumo de memória do banco

Cada pessoa cadastrada ocupa 6400 valores `double`, ou seja, 6400 x 8 = 51.200 bytes (cerca de 50 KB) na Flash. Por isso o firmware principal precisa ser gravado com a partição **Huge APP**. Esse também é o limite prático de quantas pessoas cabem no banco.

## 7. Estrutura do repositório

| Arquivo | Função | Situação |
| ----- | ----- | ----- |
| `esp-main.ino` | Firmware da ESP32 Principal (MB-LBP, distância, ESP-NOW) | Atual |
| `esp-secundaria.ino` | Firmware da ESP32 Atuadora (servo, LEDs, estados) | Atual |
| `cam.py` | Reconhecimento em tempo real, HUD, PiP e log CSV | Atual |
| `cadastrar_pessoa.py` | Captura de fotos e geração do `banco_rostos.h` | Atual |
| `capturar_minhas_fotos.py` | Captura de fotos (cadastro em etapa separada) | Fase 2, substituído |
| `processar_banco_antigo.py` | Processamento em lote das fotos antigas da turma | Fase 2, ainda útil para importar fotos antigas |
| `gerar_banco_turma.py` | Geração do banco a partir de `imagens_processadas/` | Fase 2, substituído |
| `gerar_rosto.py` | Rosto de referência com Sobel | Fase 1, obsoleto |
| `gerar_banco.py` | Banco de rostos com Sobel | Fase 1, obsoleto |

As pastas `imagens/` (fotos originais) e `imagens_processadas/` (rostos 64x64 já tratados) são usadas pelos scripts de cadastro.

## 8. Como reproduzir o projeto

### 8.1 Pré-requisitos

* Arduino IDE com suporte a placas ESP32.
* Biblioteca `ESP32Servo` (instalar pelo Gerenciador de Bibliotecas).
* Python 3 com `opencv-python`, `pyserial` e `numpy`.

**Linux (Ubuntu / Linux Mint):**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
pip3 install opencv-python pyserial numpy
```

O pacote `python3-tk` é necessário para a janela de cadastro.

**Windows:** com o Python 3 instalado (marcando "Add to PATH"):

```cmd
pip install opencv-python pyserial numpy
```

### 8.2 Gravando as placas

1. Conecte a **ESP32 Atuadora** e grave o `esp-secundaria.ino`. Se a placa não entrar em modo de gravação sozinha, segure o botão `BOOT` durante o início do upload.
2. Desconecte a atuadora e conecte a **ESP32 Principal**.
3. No `esp-main.ino`, confira se o vetor `macESP2` contém o endereço MAC da placa atuadora. Esse endereço é diferente para cada placa. Uma forma de descobri-lo é gravar um sketch simples que imprima `WiFi.macAddress()` na Serial.
4. Grave o `esp-main.ino` com a partição **Huge APP**.
5. Feche o Monitor Serial da Arduino IDE, para liberar a porta para o Python.

### 8.3 Cadastrando pessoas

```bash
python3 cadastrar_pessoa.py
```

1. Digite o nome (sem espaços) na janela que abrir.
2. Pressione `c` para tirar cada foto. Vale tirar de 5 a 10, variando levemente o ângulo e a expressão.
3. Pressione `q` para encerrar. O script recalcula o banco de todas as pessoas e atualiza `esp-main/banco_rostos.h`.
4. **Regrave a ESP32 Principal.** O banco é compilado junto com o firmware, então qualquer cadastro novo exige um novo upload.

Para importar fotos antigas de um grupo de pessoas, coloque-as em `imagens/` com nomes no formato `nome_...` e rode `processar_banco_antigo.py` antes do cadastro.

### 8.4 Executando o reconhecimento

Ajuste a variável `SERIAL_PORT` no `cam.py`:

* Windows: `COM7` (ou a porta correspondente)
* Linux: `/dev/ttyUSB0` ou `/dev/ttyACM0`

No Linux, libere o acesso à porta antes de rodar:

```bash
sudo chmod a+rw /dev/ttyUSB0
```

Depois:

```bash
python3 cam.py
```

Para encerrar, pressione `q` na janela de vídeo.

## 9. Auditoria de acessos

Cada tentativa de acesso é registrada em `relatorio_acessos.csv`, com as colunas `Data_Hora`, `Nome`, `Status` (LIBERADO ou BARRADO) e `Distancia_LBP`. Para evitar repetição, o `cam.py` grava no máximo um registro a cada 3 segundos, e não grava tentativas negadas enquanto a porta está aberta.

A interface mostra a moldura do rosto colorida conforme o estado (laranja ao processar, verde quando autorizado, vermelho quando bloqueado), o nome e a distância calculada, a taxa de quadros e uma miniatura com a imagem 64x64 tratada, que é exatamente o que a ESP32 recebe.

## 10. Limitações conhecidas e trabalhos futuros

Algumas coisas que reconheço como limitações do estado atual do projeto:

* **Limiar fixo.** O valor de 100,0 foi ajustado empiricamente depois da troca de algoritmo e não passou por uma avaliação sistemática (taxas de falso positivo e falso negativo). Um próximo passo natural seria coletar um conjunto de teste e traçar essas curvas para escolher o limiar com critério.
* **Sem detecção de vivacidade.** O sistema não distingue um rosto real de uma foto exibida na câmera. Para um uso real de segurança isso seria obrigatório.
* **ESP-NOW sem criptografia.** O par é configurado com `encrypt = false`. Qualquer dispositivo que conheça o MAC da atuadora poderia, em tese, enviar pacotes de liberação.
* **Latência não medida.** A comunicação por ESP-NOW é, em geral, de baixa latência, mas não fiz uma medição formal do tempo entre a captura da imagem e o acionamento da porta.
* **Banco embutido no firmware.** Cada novo cadastro exige regravar a ESP32 Principal. Guardar o banco em um sistema de arquivos (SPIFFS/LittleFS) permitiria atualizá-lo sem recompilar.
* **Somente o primeiro rosto.** Se houver mais de uma pessoa em quadro, apenas o primeiro rosto detectado é processado.

## 11. Considerações finais

A parte mais difícil do projeto foi o processamento de imagens. O hardware é simples: uma ESP32 que não tem nada ligado além do cabo USB e outra com um servomotor e dois LEDs. Eu já tinha alguma experiência com ESP32, então os problemas físicos, como a alimentação do motor e o conflito com o rádio, deram trabalho, mas eram problemas que eu sabia por onde começar a investigar.

Já o reconhecimento facial era território novo. Foi a primeira vez que trabalhei com processamento de imagens dessa forma, e boa parte do tempo foi gasta entendendo por que a primeira versão, com Sobel, não funcionava e o que precisava mudar. A principal lição foi que a representação da imagem importa mais do que a comparação feita depois dela: com o mesmo tipo de classificador, a troca de bordas brutas por uma imagem normalizada (Tan & Triggs) e descrita por textura (MB-LBP com histogramas por região) foi o que fez o sistema passar a funcionar. Também aprendi, na prática, por que a imagem integral é necessária para rodar esse tipo de algoritmo em um microcontrolador, e a importância de manter o código do Python e o do C++ calculando exatamente a mesma coisa.

A parte de Sistemas de Tempo Real veio como complemento a isso. Tarefas separadas por núcleo, debounce, cooldown e uma máquina de estados deixaram de ser conceito de aula quando o servo começou a tremer e a placa a reiniciar. Foram problemas menores em complexidade, mas serviram para ver, no equipamento ligado, o que acontece quando eventos chegam quase ao mesmo tempo.

O repositório mantém os scripts das fases anteriores de propósito, porque o caminho até a versão atual faz parte do trabalho.
