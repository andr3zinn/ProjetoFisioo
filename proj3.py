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

    # Máscara adaptada para o verde-azulado/ciano do adesivo
    verde_inferior = np.array([75, 80, 50])
    verde_superior = np.array([105, 255, 255])
    mascara = cv2.inRange(hsv, verde_inferior, verde_superior)

    kernel = np.ones((5, 5), np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contornos:
        maior_contorno = max(contornos, key=cv2.contourArea)
        
        if len(maior_contorno) >= 5:
            elipse = cv2.fitEllipse(maior_contorno)
            (cx, cy), (eixo_menor, eixo_maior), angulo = elipse
            
            # Cálculos em pixels
            a_px = eixo_maior / 2
            b_px = eixo_menor / 2
            excentricidade = math.sqrt(1 - (b_px**2 / a_px**2)) if a_px > 0 else 0
            area_pixels = cv2.contourArea(maior_contorno)

            # --- CÁLCULO DE DIMENSÕES REAIS (BASEADO EM 19mm NOMINAL) ---
            DIAMETRO_REAL_MM = 19.0
            
            # O maior eixo projetado representa a dimensão não-distorcida (19mm)
            escala_mm_por_pixel = DIAMETRO_REAL_MM / eixo_maior
            
            # Conversão dos eixos para milímetros
            eixo_maior_mm = DIAMETRO_REAL_MM
            eixo_menor_mm = eixo_menor * escala_mm_por_pixel
            
            # Cálculo da área real da elipse projetada em mm²
            # Area = pi * semi_eixo_maior * semi_eixo_menor
            area_real_mm2 = math.pi * (eixo_maior_mm / 2) * (eixo_menor_mm / 2)
            
            # Estimativa do ângulo de inclinação do adesivo em relação à câmera (3D)
            # cos(theta) = b/a (eixo_menor / eixo_maior)
            proporcao_eixos = eixo_menor_mm / eixo_maior_mm
            # Limita a proporção para evitar erros matemáticos fora do domínio de acos
            proporcao_eixos = min(1.0, max(0.0, proporcao_eixos))
            angulo_perspectiva_rad = math.acos(proporcao_eixos)
            angulo_perspectiva_graus = math.degrees(angulo_perspectiva_rad)

            # --- IMPRESSÃO DOS RESULTADOS ---
            print("-" * 60)
            print("🟢 RESULTADOS GEOMÉTRICOS (EM PIXELS):")
            print(f"-> Diâmetro Maior: {eixo_maior:.2f} px")
            print(f"-> Diâmetro Menor: {eixo_menor:.2f} px")
            print(f"-> Área da Máscara: {area_pixels:.2f} px²")
            print(f"-> Excentricidade (Ovalação): {excentricidade:.3f}")
            print(f"   *(0.0 = círculo perfeito | 1.0 = linha reta)*")
            print(f"-> Rotação no plano da imagem: {angulo:.1f}°")
            
            print("\n📏 METRICAS REAIS CALCULADAS (DIÂMETRO NOMINAL: 19.00 mm):")
            print(f"-> Fator de Conversão: {escala_mm_por_pixel:.4f} mm/pixel")
            print(f"-> Eixo Maior Estimado: {eixo_maior_mm:.2f} mm")
            print(f"-> Eixo Menor Estimado: {eixo_menor_mm:.2f} mm")
            print(f"-> Área Real Projetada: {area_real_mm2:.2f} mm²")
            print(f"-> Distorção Física do Formato: {((1 - proporcao_eixos) * 100):.1f}% de achatamento")
            print(f"-> Ângulo de Inclinação da Pele/Câmera: {angulo_perspectiva_graus:.1f}°")
            print("-" * 60)

            # Desenhar elipse (ciano) e centro (amarelo)
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
detectar_tratamento_ovalado('Imagens\IMG_8009.HEIC')