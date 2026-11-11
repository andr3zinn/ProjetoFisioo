import cv2
import numpy as np
import os
import math
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

def carregar_imagem_universal(caminho_imagem):
    extensao = os.path.splitext(caminho_imagem)[1].lower()
    if extensao == '.heic':
        imagem_pil = Image.open(caminho_imagem)
        imagem_rgb = np.array(imagem_pil)
        return cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2BGR)
    return cv2.imread(caminho_imagem)

def detectar_tratamento_ovalado(caminho_imagem):
    img = carregar_imagem_universal(caminho_imagem)
    if img is None:
        print("Erro ao carregar a imagem.")
        return

    imagem_saida = img.copy()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Máscara adaptativa para o verde
    verde_inferior = np.array([35, 40, 40])
    verde_superior = np.array([85, 255, 255])
    mascara = cv2.inRange(hsv, verde_inferior, verde_superior)

    kernel = np.ones((3, 3), np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contornos:
        maior_contorno = max(contornos, key=cv2.contourArea)
        
        # --- NOVO TRATAMENTO: AJUSTE DE ELIPSE ---
        # cv2.fitEllipse exige que o contorno tenha pelo menos 5 pontos
        if len(maior_contorno) >= 5:
            # elipse retorna: ((centro_x, centro_y), (eixo_menor, eixo_maior), angulo_rotacao)
            elipse = cv2.fitEllipse(maior_contorno)
            (cx, cy), (eixo_menor, eixo_maior), angulo = elipse
            
            # Cálculo da Excentricidade (métrica de ovalação)
            # e = sqrt(1 - (b²/a²)) onde a é o semi-eixo maior e b é o semi-eixo menor
            a = eixo_maior / 2
            b = eixo_menor / 2
            excentricidade = math.sqrt(1 - (b**2 / a**2)) if a > 0 else 0
            
            area_real = cv2.contourArea(maior_contorno)

            print("-" * 50)
            print("🟢 NOVO TRATAMENTO DE DADOS (FORMA OVALADA):")
            print(f"-> Diâmetro Maior (Comprimento): {eixo_maior:.2f} pixels")
            print(f"-> Diâmetro Menor (Largura): {eixo_menor:.2f} pixels")
            print(f"-> Área de Pixels Internos: {area_real:.2f} pixels²")
            print(f"-> Grau de Ovalação (Excentricidade): {excentricidade:.3f}")
            print(f"   *(0.0 = círculo perfeito | próximo de 1.0 = muito ovalado)*")
            print(f"-> Inclinação do Adesivo: {angulo:.1f}° graus")
            print("-" * 50)

            # Desenhar a elipse em azul ciano e o centro em amarelo
            cv2.ellipse(imagem_saida, elipse, (255, 255, 0), 3)
            cv2.circle(imagem_saida, (int(cx), int(cy)), 4, (0, 255, 255), -1)
        else:
            print("Contorno muito pequeno para ajustar uma elipse.")
            return

        # --- RECORTE DE ZOOM AMPLIXADO ---
        bx, by, bw, bh = cv2.boundingRect(maior_contorno)
        margem = 30
        y_ini, y_fim = max(0, by - margem), min(img.shape[0], by + bh + margem)
        x_ini, x_fim = max(0, bx - margem), min(img.shape[1], bx + bw + margem)

        zoom_real = imagem_saida[y_ini:y_fim, x_ini:x_fim]
        zoom_mascara = mascara[y_ini:y_fim, x_ini:x_fim]

        # Ajuste de telas para exibição
        altura_orig, largura_orig = img.shape[:2]
        escala = 600 / altura_orig if altura_orig > 600 else 1.0

        img_inteira_redim = cv2.resize(imagem_saida, (int(largura_orig * escala), int(altura_orig * escala)))
        
        zoom_real_ampliado = cv2.resize(zoom_real, (350, 350), interpolation=cv2.INTER_NEAREST)
        zoom_mascara_ampliado = cv2.resize(zoom_mascara, (350, 350), interpolation=cv2.INTER_NEAREST)

        # Exibição
        cv2.imshow("1. Imagem Total (Tratamento Ovalado)", img_inteira_redim)
        cv2.imshow("2. ZOOM - Elipse Ajustada", zoom_real_ampliado)
        cv2.imshow("3. ZOOM - Mascara P&B Oval", zoom_mascara_ampliado)

        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("Objeto verde não localizado.")
        cv2.destroyAllWindows()

# Executar o tratamento na imagem desejada
detectar_tratamento_ovalado('Imagens\Img1.jpeg')