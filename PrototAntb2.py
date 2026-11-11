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

print("⏳ Inicializando modelos de IA (YOLOv8x-Pose e YOLOv8x-Seg)...")
modelo_pose = YOLO("yolov8x-pose.pt")
modelo_seg = YOLO("yolov8x-seg.pt")


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


def detectar_antibraco_e_mascara_ia(img_bgr):
    """
    Detecta os pontos das articulações (Pose) e extrai a máscara 
    exata da pessoa (Segment) usando modelos profundos de IA.
    """
    h, w = img_bgr.shape[:2]

    # 1. Detecção de Pose (Articulações)
    res_pose = modelo_pose(img_bgr, verbose=False)
    if not res_pose or len(res_pose) == 0 or res_pose[0].keypoints is None:
        return None, None, None, None

    kp = res_pose[0].keypoints.data
    if len(kp) == 0:
        return None, None, None, None

    kp = kp[0]
    c_esq, p_esq = kp[7], kp[9]
    c_dir, p_dir = kp[8], kp[10]

    conf_esq = c_esq[2].item() + p_esq[2].item()
    conf_dir = c_dir[2].item() + p_dir[2].item()

    if max(conf_esq, conf_dir) < 0.5:
        return None, None, None, None

    if conf_esq > conf_dir:
        pt_cotovelo = (int(c_esq[0].item()), int(c_esq[1].item()))
        pt_punho = (int(p_esq[0].item()), int(p_esq[1].item()))
        braco = "Esquerdo"
    else:
        pt_cotovelo = (int(c_dir[0].item()), int(c_dir[1].item()))
        pt_punho = (int(p_dir[0].item()), int(p_dir[1].item()))
        braco = "Direito"

    # 2. Segmentação de Instância (Máscara do corpo)
    res_seg = modelo_seg(img_bgr, verbose=False)
    mascara_pessoa = np.zeros((h, w), dtype=np.uint8)

    if res_seg and res_seg[0].masks is not None:
        masks = res_seg[0].masks.data.cpu().numpy()
        classes = res_seg[0].boxes.cls.cpu().numpy()

        # Classe 0 no COCO é 'person'
        indices_pessoas = [i for i, c in enumerate(classes) if int(c) == 0]

        for idx in indices_pessoas:
            m = masks[idx]
            m_resized = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
            mask_binary = (m_resized > 0.5).astype(np.uint8) * 255

            # Verifica se a máscara contém o cotovelo ou o punho detectado
            cy, cx = min(h - 1, max(0, pt_cotovelo[1])), min(w - 1, max(0, pt_cotovelo[0]))
            if mask_binary[cy, cx] > 0:
                mascara_pessoa = mask_binary
                break

        # Fallback: se não coincidir exatamente, pega a primeira pessoa encontrada
        if np.sum(mascara_pessoa) == 0 and len(indices_pessoas) > 0:
            m_resized = cv2.resize(masks[indices_pessoas[0]], (w, h), interpolation=cv2.INTER_LINEAR)
            mascara_pessoa = (m_resized > 0.5).astype(np.uint8) * 255

    return pt_cotovelo, pt_punho, braco, mascara_pessoa


def isolar_mascara_antibraco(mascara_pessoa, pt_cotovelo, pt_punho, img_shape):
    """Combina a máscara IA da pessoa com o corredor geométrico do antebraço."""
    dx = pt_punho[0] - pt_cotovelo[0]
    dy = pt_punho[1] - pt_cotovelo[1]
    distancia = math.hypot(dx, dy)

    corredor = np.zeros(img_shape[:2], dtype=np.uint8)
    largura_corredor = int(distancia * 0.40)
    cv2.line(corredor, pt_cotovelo, pt_punho, 255, thickness=largura_corredor)

    # Interseção direta entre a pessoa segmentada pela IA e o corredor
    mascara_antibraco = cv2.bitwise_and(mascara_pessoa, corredor)

    # Suavização leve das bordas
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mascara_antibraco = cv2.morphologyEx(mascara_antibraco, cv2.MORPH_CLOSE, kernel)

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

    ux, uy = dx / distancia_total_px, dy / distancia_total_px
    nx, ny = -uy, ux

    intervalo_px = 50.0 * px_por_mm  # 5cm em pixels
    px_por_cm = px_por_mm * 10.0
    fator_area_cm2 = px_por_cm ** 2

    cortes = []
    d = 0.0
    while d < distancia_total_px:
        cortes.append(d)
        d += intervalo_px
    cortes.append(distancia_total_px)

    cores_fatias = [
        (255, 99, 71),   # Tomate
        (50, 205, 50),   # Verde Lima
        (30, 144, 255),  # Azul
        (255, 215, 0),   # Dourado
        (147, 112, 219), # Roxo
        (255, 105, 180), # Rosa
        (0, 206, 209),   # Ciano
    ]

    W = max(img.shape[:2]) * 2

    print("\n--- 📐 MEDIÇÃO DE ÁREAS POR SEGMENTO ---")

    for i in range(len(cortes) - 1):
        d_inicio = cortes[i]
        d_fim = cortes[i + 1]

        p1 = (pt_cotovelo[0] + ux * d_inicio, pt_cotovelo[1] + uy * d_inicio)
        p2 = (pt_cotovelo[0] + ux * d_fim, pt_cotovelo[1] + uy * d_fim)

        v1 = (int(p1[0] + nx * W), int(p1[1] + ny * W))
        v2 = (int(p2[0] + nx * W), int(p2[1] + ny * W))
        v3 = (int(p2[0] - nx * W), int(p2[1] - ny * W))
        v4 = (int(p1[0] - nx * W), int(p1[1] - ny * W))

        mascara_fatia = np.zeros(img.shape[:2], dtype=np.uint8)
        pts_poly = np.array([v1, v2, v3, v4], dtype=np.int32)
        cv2.fillPoly(mascara_fatia, [pts_poly], 255)

        fatia_antibraco = cv2.bitwise_and(mascara_braco, mascara_fatia)

        area_pixels = cv2.countNonZero(fatia_antibraco)
        area_cm2 = area_pixels / fator_area_cm2

        cor = cores_fatias[i % len(cores_fatias)]

        overlay[fatia_antibraco > 0] = cor

        contours, _ = cv2.findContours(fatia_antibraco, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img_resultado, contours, -1, (255, 255, 255), 2)

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

    cv2.addWeighted(overlay, 0.4, img_resultado, 0.6, 0, img_resultado)

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

    # 2. Localizar articulações e segmentação via IA
    print("🤖 Analisando estrutura anatômica e segmentando o corpo...")
    pt_cotovelo, pt_punho, braco, mascara_pessoa = detectar_antibraco_e_mascara_ia(img)

    if pt_cotovelo is None or np.sum(mascara_pessoa) == 0:
        print("❌ Não foi possível identificar o braço ou a pessoa na foto.")
    else:
        print(f"✅ Braço {braco} e silhueta detectados via IA! Calculando áreas...")

        # 3. Mapear contorno exato do antebraço sem depender de filtro de cor
        mascara_braco = isolar_mascara_antibraco(mascara_pessoa, pt_cotovelo, pt_punho, img.shape)
        img_exibicao = segmentar_areas_antibraco(img_exibicao, pt_cotovelo, pt_punho, px_por_mm, mascara_braco)

    # 4. Exibição
    h_orig, w_orig = img_exibicao.shape[:2]
    altura_desejada = 850
    fator_escala = altura_desejada / float(h_orig)
    largura_desejada = int(w_orig * fator_escala)

    cv2.namedWindow("Segmentacao por Area do Antibraco (IA)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Segmentacao por Area do Antibraco (IA)", largura_desejada, altura_desejada)
    cv2.imshow("Segmentacao por Area do Antibraco (IA)", img_exibicao)
    print("\n👉 Pressione qualquer tecla na janela aberta para encerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("imagem", help="Caminho para o arquivo de imagem")
    parser.add_argument("--diametro-mm", type=float, default=19.0, help="Diâmetro do marcador em mm")
    args = parser.parse_args()

    main(args.imagem, args.diametro_mm)