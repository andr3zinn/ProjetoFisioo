"""
Detecção em lote da tag verde (marcador circular) para calibração px -> mm.

Roda a detecção em TODAS as imagens de uma pasta, imprime um resumo em
tabela com as medidas em pixels de cada uma, e salva uma imagem de
depuração (elipse + bounding box desenhadas).

Uso:
    python3 nome_do_script.py [--pasta Imagens] [--saida-dir debug/] [--diametro-mm 19]
"""

import argparse
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

# Registra o abridor de HEIF/HEIC no Pillow
register_heif_opener()

# Adicionado .heic na lista de suportados
EXTENSOES_SUPORTADAS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heic")


def ler_imagem(caminho_imagem):
    """Lê a imagem, suportando nativamente HEIC através do Pillow e retornando no padrão OpenCV (BGR)."""
    ext = os.path.splitext(caminho_imagem)[1].lower()
    
    if ext == ".heic":
        try:
            # Abre usando o Pillow (com suporte do pillow_heif) e converte para BGR do OpenCV
            pil_img = Image.open(caminho_imagem).convert('RGB')
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            return img_bgr
        except Exception as e:
            print(f"Erro ao abrir arquivo HEIC {caminho_imagem}: {e}")
            return None
    else:
        # Usa o OpenCV tradicional para as outras extensões
        return cv2.imread(caminho_imagem)


def detectar_tag_verde(img_bgr, hsv_lower=(35, 60, 40), hsv_upper=(85, 255, 255),
                       area_min_frac=0.00005, area_max_frac=0.05):
    """Retorna (contorno, ellipse, mask) do maior blob verde plausível, ou (None, None, mask)."""
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


def medir_tag_em_imagem(caminho_imagem, diametro_real_mm=None):
    img = ler_imagem(caminho_imagem)
    if img is None:
        return None, None, "Não foi possível abrir a imagem (formato corrompido ou não suportado)"

    contorno, ellipse, mask = detectar_tag_verde(img)
    if ellipse is None:
        return None, img, "Nenhuma tag verde encontrada"

    (cx, cy), (eixo1, eixo2), angulo = ellipse
    eixo_maior_px = max(eixo1, eixo2)
    eixo_menor_px = min(eixo1, eixo2)
    x, y, w_bb, h_bb = cv2.boundingRect(contorno)

    resultado = {
        "arquivo": os.path.basename(caminho_imagem),
        "resolucao": f"{img.shape[1]}x{img.shape[0]}",
        "centro_px": (round(cx, 1), round(cy, 1)),
        "eixo_maior_elipse_px": round(eixo_maior_px, 2),
        "eixo_menor_elipse_px": round(eixo_menor_px, 2),
        "largura_bbox_px": w_bb,
        "altura_bbox_px": h_bb,
        "angulo_graus": round(angulo, 1),
    }

    if diametro_real_mm:
        diametro_medio_px = (eixo_maior_px + eixo_menor_px) / 2
        px_por_mm = diametro_medio_px / diametro_real_mm
        resultado["diametro_medio_px"] = round(diametro_medio_px, 2)
        resultado["px_por_mm"] = round(px_por_mm, 4)
        resultado["mm_por_px"] = round(1 / px_por_mm, 5)

    debug = img.copy()
    cv2.ellipse(debug, ellipse, (0, 0, 255), 3)
    cv2.rectangle(debug, (x, y), (x + w_bb, y + h_bb), (255, 0, 0), 2)
    cv2.drawMarker(debug, (int(cx), int(cy)), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
    texto = f"maior={eixo_maior_px:.1f}px  menor={eixo_menor_px:.1f}px"
    cv2.putText(debug, texto, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

    return resultado, debug, None


def processar_pasta(pasta, saida_dir="debug_out", diametro_real_mm=None):
    os.makedirs(saida_dir, exist_ok=True)

    arquivos = sorted(
        f for f in glob.glob(os.path.join(pasta, "*"))
        if f.lower().endswith(EXTENSOES_SUPORTADAS)
    )

    if not arquivos:
        print(f"Nenhuma imagem suportada encontrada na pasta: '{pasta}'")
        return []

    resultados = []
    print(f"{'arquivo':<30} {'resolução':<12} {'eixo maior(px)':<16} {'eixo menor(px)':<16} {'bbox WxH':<12}")
    print("-" * 90)

    for caminho in arquivos:
        resultado, debug, erro = medir_tag_em_imagem(caminho, diametro_real_mm)

        if erro:
            print(f"{os.path.basename(caminho):<30} ERRO: {erro}")
            continue

        print(
            f"{resultado['arquivo']:<30} "
            f"{resultado['resolucao']:<12} "
            f"{resultado['eixo_maior_elipse_px']:<16} "
            f"{resultado['eixo_menor_elipse_px']:<16} "
            f"{resultado['largura_bbox_px']}x{resultado['altura_bbox_px']}"
        )

        nome_saida = os.path.splitext(resultado["arquivo"])[0] + "_debug.png"
        # Garante que salva os outputs em PNG/JPG mesmo que a entrada seja HEIC
        cv2.imwrite(os.path.join(saida_dir, nome_saida), debug)
        resultados.append(resultado)

    return resultados


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # Alterado para ter "Imagens" como valor padrão
    ap.add_argument("--pasta", default="Imagens", help="Pasta contendo as imagens a processar (padrão: Imagens)")
    ap.add_argument("--saida-dir", default="debug_out", help="Pasta onde salvar as imagens de depuração (padrão: debug_out)")
    ap.add_argument("--diametro-mm", type=float, default=None,
                    help="Diâmetro real da tag em mm, para converter px em mm")
    args = ap.parse_args()

    processar_pasta(args.pasta, args.saida_dir, args.diametro_mm)