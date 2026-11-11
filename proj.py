
import cv2
import numpy as np

def detectar_e_mostrar_mascara(caminho_imagem):
    """
    Detecta uma bolinha verde brilhante em uma imagem usando segmentação por cor no espaço HSV.
    Calcula o diâmetro em pixels e exibe a máscara de cor final e a imagem de resultado.
    """
    # 1. Carregar a imagem
    img = cv2.imread(caminho_imagem)
    if img is None:
        print("Erro: Imagem não encontrada. Verifique o caminho.")
        return

    imagem_saida = img.copy()

    # 2. Converter a imagem do espaço BGR (padrão do OpenCV) para HSV
    # O espaço HSV separa a cor (Matiz/Hue) da iluminação, tornando a detecção mais robusta
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 3. Definir os limites inferior e superior para a cor verde vibrante
    # O verde no OpenCV vai de ~40 a 80 no canal H (Hue)
    verde_inferior = np.array([40, 100, 100])
    verde_superior = np.array([85, 255, 255])

    # 4. Criar uma máscara que isola apenas os pixels dentro do intervalo verde
    mascara = cv2.inRange(hsv, verde_inferior, verde_superior)

    # 5. Aplicar operações morfológicas para limpar ruídos (suavização)
    # Isso remove pequenos pontos verdes falsos e preenche falhas na bolinha
    kernel = np.ones((5, 5), np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)

    # --- PASSO ADICIONADO: Redimensionar e exibir a máscara ---
    # Obter dimensões para redimensionamento de exibição
    altura_orig, largura_orig = mascara.shape[:2]
    escala = 1.0
    if altura_orig > 800:
        escala = 800 / altura_orig
    
    mascara_para_exibir = cv2.resize(mascara.copy(), (int(largura_orig * escala), int(altura_orig * escala)))
    
    # Exibir a janela da máscara (Branco é a cor verde detectada, Preto é todo o resto)
    cv2.imshow("Mascara de Detecção (Branco = Verde)", mascara_para_exibir)
    # -----------------------------------------------------------

    # 6. Encontrar os contornos dos objetos brancos na máscara
    # Usamos cv2.RETR_EXTERNAL para pegar apenas o contorno mais externo de cada forma
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contornos:
        # 7. Assumir que a bolinha verde é o maior contorno detectado na máscara
        maior_contorno = max(contornos, key=cv2.contourArea)

        # 8. Calcular o círculo mínimo que envolve o contorno
        # O círculo circunscrito perfeito ajuda a lidar com distorções na forma orgânica
        ((x, y), raio) = cv2.minEnclosingCircle(maior_contorno)

        # 9. Calcular o diâmetro matemático
        # Fórmula: D = 2 * r
        diametro_pixels = raio * 2

        print(f"Sucesso! Bolinha verde detectada.")
        print(f"-> Diâmetro exato: {diametro_pixels:.2f} pixels")
        print(f"-> Posição (X, Y): ({int(x)}, {int(y)})")

        # 10. Desenhar o resultado na imagem original (cópia) para validação visual
        # Desenha o círculo delimitador em vermelho e o centro em amarelo
        cv2.circle(imagem_saida, (int(x), int(y)), int(raio), (0, 0, 255), 2) # Círculo vermelho
        cv2.circle(imagem_saida, (int(x), int(y)), 3, (0, 255, 255), -1)   # Centro amarelo

        # Redimensionar a imagem de saída para exibição, se necessário
        if altura_orig > 800:
            imagem_saida_para_exibir = cv2.resize(imagem_saida, (int(largura_orig * escala), int(altura_orig * escala)))
        else:
            imagem_saida_para_exibir = imagem_saida

        # Exibir a janela do resultado final com o círculo de detecção
        cv2.imshow("Bolinha Verde Detectada (Resultado)", imagem_saida_para_exibir)
        
        # Aguardar que o usuário feche as janelas (pressione qualquer tecla)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("Nenhuma bolinha verde foi detectada com os parâmetros atuais.")
        # Limpar janelas mesmo se a bolinha não for detectada



detectar_e_mostrar_mascara("Img1.jpeg")
