"""
Script para análise visual e medição de UMA ÚNICA imagem.
Exibe a imagem anotada, a máscara verde e as medições no terminal.

Uso:
    python3 analisar_uma_imagem.py Imagens/IMG_2558.HEIC
    python3 analisar_uma_imagem.py Imagens/Img.jpeg --diametro-mm 19
"""

import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

# Habilita suporte a HEIC no Pillow
register_heif_opener()


def ler_imagem(caminho_imagem):
    """Lê a imagem (JPG, PNG, HEIC, etc.) e converte para BGR do OpenCV."""
    if not os.path.exists(caminho_imagem):
        print(f"\n❌ ERRO: O arquivo '{caminho_imagem}' não foi encontrado.")
        return None

    ext = os.path.splitext(caminho_imagem)[1].lower()

    if ext in (".heic", ".heif"):
        try:
            pil_img = Image.open(caminho_imagem).convert("RGB")
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"\n❌ ERRO ao abrir o arquivo HEIC ({caminho_imagem}): {e}")
            return None
    else:
        img = cv2.imread(caminho_imagem)
        if img is None:
            print(f"\n❌ ERRO ao abrir a imagem com OpenCV: {caminho_imagem}")
        return img


def detectar_tag_verde(img_bgr, hsv_lower=(35, 60, 40), hsv_upper=(85, 255, 255),
                       area_min_frac=0.00005, area_max_frac=0.05):
    """Filtra a cor verde e encontra a melhor elipse/contorno circular."""
    h, w = img_bgr.shape[:2]
    img_area = h * w

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_lower), np.array(hsv_upper))

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidatos = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < area_min_frac * img_area or area > area_max_frac * img_area:
            continue
        if len(c) < 5:
            continue
        perimetro = cv2.arcLength(c, True)
        if perimetro == 0:
            continue
        circularidade = 4 * np.pi * area / (perimetro ** 2)
        if circularidade < 0.5:
            continue
        candidatos.append((area, circularidade, c))

    if not candidatos:
        return None, None, mask

    candidatos.sort(key=lambda t: t[0], reverse=True)
    _, _, melhor_contorno = candidatos[0]
    ellipse = cv2.fitEllipse(melhor_contorno)

    return melhor_contorno, ellipse, mask


def analisar_imagem(caminho_imagem, diametro_real_mm=None):
    img = ler_imagem(caminho_imagem)
    if img is None:
        return

    contorno, ellipse, mask = detectar_tag_verde(img)
    img_anotada = img.copy()

    print("\n" + "=" * 55)
    print(f" 📊 RELATÓRIO DE MEDIÇÃO: {os.path.basename(caminho_imagem)}")
    print("=" * 55)
    print(f"• Resolução da imagem : {img.shape[1]} x {img.shape[0]} px")

    if ellipse is None:
        print("\n❌ Nenhuma tag verde foi encontrada na imagem!")
        print("Dica: Verifique se a iluminação ou os limites HSV precisam de ajuste.")
    else:
        (cx, cy), (eixo1, eixo2), angulo = ellipse
        eixo_maior_px = max(eixo1, eixo2)
        eixo_menor_px = min(eixo1, eixo2)
        x, y, w_bb, h_bb = cv2.boundingRect(contorno)

        # Anotações na imagem
        cv2.ellipse(img_anotada, ellipse, (0, 0, 255), 3)                  # Elipse (Vermelho)
        cv2.rectangle(img_anotada, (x, y), (x + w_bb, y + h_bb), (255, 0, 0), 2)  # Box (Azul)
        cv2.drawMarker(img_anotada, (int(cx), int(cy)), (0, 255, 255), cv2.MARKER_CROSS, 25, 2) # Centro (Amarelo)

        texto = f"Eixo maior: {eixo_maior_px:.1f}px | Eixo menor: {eixo_menor_px:.1f}px"
        cv2.putText(img_anotada, texto, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        print("\n✅ Tag verde detectada!")
        print(f"• Centro (X, Y)       : ({round(cx, 1)}, {round(cy, 1)}) px")
        print(f"• Eixo Maior Elipse   : {round(eixo_maior_px, 2)} px")
        print(f"• Eixo Menor Elipse   : {round(eixo_menor_px, 2)} px")
        print(f"• Bounding Box (WxH)  : {w_bb} x {h_bb} px")
        print(f"• Ângulo de Inclinação: {round(angulo, 1)}°")

        if diametro_real_mm:
            diametro_medio_px = (eixo_maior_px + eixo_menor_px) / 2
            px_por_mm = diametro_medio_px / diametro_real_mm
            mm_por_px = 1 / px_por_mm
            print("-" * 55)
            print(f"• Diâmetro Médio      : {round(diametro_medio_px, 2)} px")
            print(f"• Escala (px/mm)      : {round(px_por_mm, 4)} px/mm")
            print(f"• Escala (mm/px)      : {round(mm_por_px, 5)} mm/px")

    print("=" * 55)
    print("👉 Janelas exibidas. Pressione QUALQUER TECLA sobre as imagens para fechar.\n")

    # Criar janelas redimensionáveis (útil para fotos de alta resolução)
    cv2.namedWindow("1 - Imagem Anotada", cv2.WINDOW_NORMAL)
    cv2.namedWindow("2 - Mascara Verde", cv2.WINDOW_NORMAL)

    # Ajusta o tamanho inicial das janelas na tela
    cv2.resizeWindow("1 - Imagem Anotada", 800, 600)
    cv2.resizeWindow("2 - Mascara Verde", 800, 600)

    cv2.imshow("1 - Imagem Anotada", img_anotada)
    cv2.imshow("2 - Mascara Verde", mask)

    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Testa a detecção em uma imagem específica.")
    parser.add_argument("imagem", help="Caminho completo ou relativo para a imagem")
    parser.add_argument("--diametro-mm", type=float, default=None, help="Diâmetro real da tag em mm")

    args = parser.parse_args()
    analisar_imagem(args.imagem, args.diametro_mm)