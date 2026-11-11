import argparse
import math
import os

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener
from ultralytics import YOLO

# Registra suporte para arquivos HEIC/HEIF
register_heif_opener()

print("⏳ Inicializando modelo de IA (YOLOv8x)...")
modelo_ia = YOLO("yolov8x-pose.pt")


def ler_imagem(caminho_imagem):
    """Carrega imagens no formato JPG, PNG ou HEIC."""
    if not os.path.exists(caminho_imagem):
        print(f"❌ ERRO: O arquivo '{caminho_imagem}' não foi encontrado.")
        return None

    ext = os.path.splitext(caminho_imagem)[1].lower()
    if ext in (".heic", ".heif"):
        try:
            pil_img = Image.open(caminho_imagem).convert("RGB")
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"❌ ERRO ao abrir a imagem HEIC: {e}")
            return None
    else:
        return cv2.imread(caminho_imagem)


def detectar_tag_verde(img_bgr, hsv_lower=(35, 60, 40), hsv_upper=(85, 255, 255)):
    """Detecta a tag verde e calcula a escala de pixels por milímetro."""
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
        if area < 0.00005 * img_area or area > 0.05 * img_area:
            continue
        perimetro = cv2.arcLength(c, True)
        if perimetro == 0:
            continue
        circularidade = 4 * np.pi * area / (perimetro ** 2)
        if circularidade > 0.5:
            candidatos.append((area, c))

    if not candidatos:
        return None

    candidatos.sort(key=lambda t: t[0], reverse=True)
    return cv2.fitEllipse(candidatos[0][1])


def detectar_antibraco_ia(img_bgr):
    """Detecta os pontos centrais do cotovelo e punho."""
    resultados = modelo_ia(img_bgr, verbose=False)

    if not resultados or len(resultados) == 0:
        return None, None, None

    keypoints = resultados[0].keypoints
    if keypoints is None or len(keypoints.data) == 0:
        return None, None, None

    kp = keypoints.data[0]

    # COCO Pose: 7=Cotovelo Esq, 9=Punho Esq, 8=Cotovelo Dir, 10=Punho Dir
    c_esq, p_esq = kp[7], kp[9]
    c_dir, p_dir = kp[8], kp[10]

    conf_esq = c_esq[2].item() + p_esq[2].item()
    conf_dir = c_dir[2].item() + p_dir[2].item()

    if max(conf_esq, conf_dir) < 0.5:
        return None, None, None

    if conf_esq > conf_dir:
        pt_cotovelo = (int(c_esq[0].item()), int(c_esq[1].item()))
        pt_punho = (int(p_esq[0].item()), int(p_esq[1].item()))
        braco = "Esquerdo"
    else:
        pt_cotovelo = (int(c_dir[0].item()), int(c_dir[1].item()))
        pt_punho = (int(p_dir[0].item()), int(p_dir[1].item()))
        braco = "Direito"

    return pt_cotovelo, pt_punho, braco


def isolar_mascara_antibraco(img_bgr, pt_cotovelo, pt_punho):
    """Segmenta a pele do antebraço limitando a busca ao corredor do braço."""
    ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # Filtro de tom de pele em duplo espaço de cor
    mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
    mask_hsv = cv2.inRange(hsv, np.array([0, 15, 40]), np.array([25, 255, 255]))
    mask_pele = cv2.bitwise_and(mask_ycrcb, mask_hsv)

    # Cria corredor limitador ao redor do antebraço
    dx = pt_punho[0] - pt_cotovelo[0]
    dy = pt_punho[1] - pt_cotovelo[1]
    distancia = math.hypot(dx, dy)

    corredor = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
    largura_corredor = int(distancia * 0.45)
    cv2.line(corredor, pt_cotovelo, pt_punho, 255, thickness=largura_corredor)

    # Aplica o corredor
    mascara_antibraco = cv2.bitwise_and(mask_pele, corredor)

    # Fechamento morfológico para uniformizar a máscara da pele
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mascara_antibraco = cv2.morphologyEx(mascara_antibraco, cv2.MORPH_CLOSE, kernel, iterations=2)
    mascara_antibraco = cv2.morphologyEx(mascara_antibraco, cv2.MORPH_OPEN, kernel, iterations=1)

    return mascara_antibraco


def segmentar_areas_antibraco(img, pt_cotovelo, pt_punho, px_por_mm, mascara_braco):
    """Divide a máscara do antebraço em fatias perpendiculares a cada 5cm e calcula as áreas."""
    img_resultado = img.copy()
    overlay = img.copy()

    dx = pt_punho[0] - pt_cotovelo[0]
    dy = pt_punho[1] - pt_cotovelo[1]
    distancia_total_px = math.hypot(dx, dy)

    if distancia_total_px == 0:
        return img

    # Vetor unitário diretor (u) e normal/perpendicular (n)
    ux, uy = dx / distancia_total_px, dy / distancia_total_px
    nx, ny = -uy, ux

    intervalo_px = 50.0 * px_por_mm  # 5cm em pixels
    px_por_cm = px_por_mm * 10.0
    fator_area_cm2 = px_por_cm ** 2  # Conversão de px² para cm²

    # Gera posições de corte ao longo do braço (incluindo o início e a ponta final)
    cortes = []
    d = 0.0
    while d < distancia_total_px:
        cortes.append(d)
        d += intervalo_px
    cortes.append(distancia_total_px)

    # Paleta de cores vibrantes para distinguir as áreas N
    cores_fatias = [
        (255, 99, 71),   # Tomate
        (50, 205, 50),   # Verde Lima
        (30, 144, 255),  # Azul
        (255, 215, 0),   # Dourado
        (147, 112, 219), # Roxo
        (255, 105, 180), # Rosa
        (0, 206, 209),   # Ciano
    ]

    W = max(img.shape[:2]) * 2  # Comprimento suficiente para cortar toda a largura do braço

    print("\n--- 📐 MEDIÇÃO DE ÁREAS POR SEGMENTO ---")

    for i in range(len(cortes) - 1):
        d_inicio = cortes[i]
        d_fim = cortes[i + 1]

        # Pontos centrais dos cortes
        p1 = (pt_cotovelo[0] + ux * d_inicio, pt_cotovelo[1] + uy * d_inicio)
        p2 = (pt_cotovelo[0] + ux * d_fim, pt_cotovelo[1] + uy * d_fim)

        # Vértices do polígono do corte perpendicular
        v1 = (int(p1[0] + nx * W), int(p1[1] + ny * W))
        v2 = (int(p2[0] + nx * W), int(p2[1] + ny * W))
        v3 = (int(p2[0] - nx * W), int(p2[1] - ny * W))
        v4 = (int(p1[0] - nx * W), int(p1[1] - ny * W))

        # Cria a máscara para o trecho N
        mascara_fatia = np.zeros(img.shape[:2], dtype=np.uint8)
        pts_poly = np.array([v1, v2, v3, v4], dtype=np.int32)
        cv2.fillPoly(mascara_fatia, [pts_poly], 255)

        # Interseção da fatia com a pele do antebraço
        fatia_antibraco = cv2.bitwise_and(mascara_braco, mascara_fatia)

        # Cálculo da Área do segmento em cm²
        area_pixels = cv2.countNonZero(fatia_antibraco)
        area_cm2 = area_pixels / fator_area_cm2

        # Cor do segmento
        cor = cores_fatias[i % len(cores_fatias)]

        # Pinta a área segmentada no overlay
        overlay[fatia_antibraco > 0] = cor

        # Desenha o contorno exato da borda do braço naquele segmento
        contours, _ = cv2.findContours(fatia_antibraco, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img_resultado, contours, -1, (255, 255, 255), 2)

        # Texto informativo da Área
        cm_ini = (d_inicio / px_por_mm) / 10.0
        cm_fim = (d_fim / px_por_mm) / 10.0
        
        centro_x = int((p1[0] + p2[0]) / 2)
        centro_y = int((p1[1] + p2[1]) / 2)

        texto_area = f"A{i+1}: {area_cm2:.1f} cm2"
        cv2.putText(img_resultado, texto_area, (centro_x - 50, centro_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(img_resultado, texto_area, (centro_x - 50, centro_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        print(f"🔸 Área {i+1} ({cm_ini:.1f}cm a {cm_fim:.1f}cm): {area_cm2:.2f} cm²")

    # Transparência suave (50% imagem original, 50% máscara colorida)
    cv2.addWeighted(overlay, 0.4, img_resultado, 0.6, 0, img_resultado)

    # Desenha a linha central (Azul)
    cv2.line(img_resultado, pt_cotovelo, pt_punho, (255, 0, 0), 2)
    cv2.circle(img_resultado, pt_cotovelo, 7, (0, 0, 255), -1)
    cv2.circle(img_resultado, pt_punho, 7, (0, 165, 255), -1)

    return img_resultado


def main(caminho_imagem, diametro_real_mm):
    img = ler_imagem(caminho_imagem)
    if img is None:
        return

    img_exibicao = img.copy()

    # 1. Encontrar tag verde
    ellipse = detectar_tag_verde(img)
    if ellipse is None:
        print("❌ Tag verde não encontrada. Impossível calcular a escala.")
        return

    eixo_maior = max(ellipse[1][0], ellipse[1][1])
    eixo_menor = min(ellipse[1][0], ellipse[1][1])
    px_por_mm = ((eixo_maior + eixo_menor) / 2) / diametro_real_mm
    print(f"✅ Tag verde detectada! Escala: {px_por_mm:.2f} pixels/mm")

    cv2.ellipse(img_exibicao, ellipse, (0, 255, 255), 3)

    # 2. Localizar articulações com a IA
    print("🤖 Analisando estrutura anatômica...")
    pt_cotovelo, pt_punho, braco = detectar_antibraco_ia(img)

    if pt_cotovelo is None:
        print("❌ Não foi possível identificar o braço na foto.")
    else:
        print(f"✅ Braço {braco} detectado! Gerando máscaras e calculando áreas...")
        
        # 3. Mapear contorno do antebraço e fatiar em N áreas de 5cm
        mascara_braco = isolar_mascara_antibraco(img, pt_cotovelo, pt_punho)
        img_exibicao = segmentar_areas_antibraco(img_exibicao, pt_cotovelo, pt_punho, px_por_mm, mascara_braco)

    # 4. Exibição mantendo o Aspect Ratio da câmera
    h_orig, w_orig = img_exibicao.shape[:2]
    altura_desejada = 850
    fator_escala = altura_desejada / float(h_orig)
    largura_desejada = int(w_orig * fator_escala)

    cv2.namedWindow("Segmentacao por Area do Antibraco", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Segmentacao por Area do Antibraco", largura_desejada, altura_desejada)
    cv2.imshow("Segmentacao por Area do Antibraco", img_exibicao)
    print("\n👉 Pressione qualquer tecla na janela aberta para encerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("imagem", help="Caminho para o arquivo de imagem")
    parser.add_argument("--diametro-mm", type=float, default=19.0, help="Diâmetro do marcador em mm")
    args = parser.parse_args()

    main(args.imagem, args.diametro_mm)