import argparse
import math
import os

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener
from ultralytics import YOLO

register_heif_opener()

print("⏳ Inicializando modelos de IA (YOLO11x-Pose e YOLO11x-Seg)...")
modelo_pose = YOLO("yolo11x-pose.pt")
modelo_seg = YOLO("yolo11x-seg.pt")


def ler_imagem(caminho_imagem):
    """Carrega imagens nos formatos JPG, PNG ou HEIC."""
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
    """Detecta a tag verde para calcular a escala em pixels por milímetro."""
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


def processar_fallback_close_up(img_bgr):
    """
    Fallback executado quando a foto é aproximada (close-up) e o YOLO não acha o corpo.
    Segmenta o maior bloco de pele e estima o eito superior/inferior.
    """
    ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
    mask_hsv = cv2.inRange(hsv, np.array([0, 15, 40]), np.array([25, 255, 255]))
    mask_pele = cv2.bitwise_and(mask_ycrcb, mask_hsv)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask_pele = cv2.morphologyEx(mask_pele, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask_pele = cv2.morphologyEx(mask_pele, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask_pele, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, None

    maior_contorno = max(contours, key=cv2.contourArea)
    mascara_braco = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
    cv2.drawContours(mascara_braco, [maior_contorno], -1, 255, thickness=cv2.FILLED)

    pts = maior_contorno.reshape(-1, 2)
    
    # Define extremidade superior e inferior do braço enquadrado
    idx_topo = np.argmin(pts[:, 1])
    idx_base = np.argmax(pts[:, 1])

    pt_cotovelo = tuple(map(int, pts[idx_topo]))
    pt_punho = tuple(map(int, pts[idx_base]))

    return mascara_braco, pt_cotovelo, pt_punho


def detectar_antibracos_e_mascara_ia(img_bgr):
    """Detecta braços via YOLO11. Reduz limiar de confiança para fotos parciais."""
    h, w = img_bgr.shape[:2]
    bracos_detectados = []

    res_pose = modelo_pose(img_bgr, verbose=False)
    if res_pose and len(res_pose) > 0 and res_pose[0].keypoints is not None:
        for kp_pessoa in res_pose[0].keypoints.data:
            if len(kp_pessoa) >= 11:
                c_esq, p_esq = kp_pessoa[7], kp_pessoa[9]
                c_dir, p_dir = kp_pessoa[8], kp_pessoa[10]

                # Limiar ajustado para 0.25 para capturar visões parciais
                if c_esq[2].item() > 0.25 and p_esq[2].item() > 0.25:
                    bracos_detectados.append({
                        "lado": "Esquerdo",
                        "cotovelo": (int(c_esq[0].item()), int(c_esq[1].item())),
                        "punho": (int(p_esq[0].item()), int(p_esq[1].item()))
                    })

                if c_dir[2].item() > 0.25 and p_dir[2].item() > 0.25:
                    bracos_detectados.append({
                        "lado": "Direito",
                        "cotovelo": (int(c_dir[0].item()), int(c_dir[1].item())),
                        "punho": (int(p_dir[0].item()), int(p_dir[1].item()))
                    })

    res_seg = modelo_seg(img_bgr, verbose=False)
    mascara_pessoas = np.zeros((h, w), dtype=np.uint8)

    if res_seg and res_seg[0].masks is not None:
        masks = res_seg[0].masks.data.cpu().numpy()
        classes = res_seg[0].boxes.cls.cpu().numpy()

        for idx, cls_id in enumerate(classes):
            if int(cls_id) == 0:
                m = masks[idx]
                m_resized = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
                mask_binary = (m_resized > 0.5).astype(np.uint8) * 255
                mascara_pessoas = cv2.bitwise_or(mascara_pessoas, mask_binary)

    return bracos_detectados, mascara_pessoas


def isolar_mascara_antibraco(mascara_pessoa, pt_cotovelo, pt_punho, img_shape):
    """Aplica o corredor geométrico sobre a máscara para isolar o segmento."""
    dx = pt_punho[0] - pt_cotovelo[0]
    dy = pt_punho[1] - pt_cotovelo[1]
    distancia = math.hypot(dx, dy)

    corredor = np.zeros(img_shape[:2], dtype=np.uint8)
    largura_corredor = int(distancia * 0.35)
    cv2.line(corredor, pt_cotovelo, pt_punho, 255, thickness=largura_corredor)

    mascara_antibraco = cv2.bitwise_and(mascara_pessoa, corredor)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    return cv2.morphologyEx(mascara_antibraco, cv2.MORPH_CLOSE, kernel)


def segmentar_areas_antibraco(img, pt_cotovelo, pt_punho, px_por_mm, mascara_braco, lado_braco):
    """Calcula as fatias a cada 5cm e plota na imagem."""
    img_resultado = img.copy()
    overlay = img.copy()

    dx = pt_punho[0] - pt_cotovelo[0]
    dy = pt_punho[1] - pt_cotovelo[1]
    distancia_total_px = math.hypot(dx, dy)

    if distancia_total_px == 0:
        return img

    ux, uy = dx / distancia_total_px, dy / distancia_total_px
    nx, ny = -uy, ux

    intervalo_px = 50.0 * px_por_mm
    fator_area_cm2 = (px_por_mm * 10.0) ** 2

    cortes = []
    d = 0.0
    while d < distancia_total_px:
        cortes.append(d)
        d += intervalo_px
    cortes.append(distancia_total_px)

    cores_fatias = [
        (255, 99, 71),   (50, 205, 50),   (30, 144, 255),
        (255, 215, 0),   (147, 112, 219), (255, 105, 180), (0, 206, 209)
    ]

    W = max(img.shape[:2]) * 2
    print(f"\n--- 📐 MEDIÇÃO: BRAÇO {lado_braco.upper()} ---")

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
        cv2.putText(img_resultado, texto_area, (centro_x - 50, centro_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(img_resultado, texto_area, (centro_x - 50, centro_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

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

    # 2. Tentar detecção via IA
    print("🤖 Analisando estrutura anatômica via IA...")
    bracos, mascara_pessoa = detectar_antibracos_e_mascara_ia(img)

    # Fallback se a IA falhar em fotos close-up
    if not bracos or np.sum(mascara_pessoa) == 0:
        print("⚠️ Visão geral corporal indisponível (modo Close-Up). Ativando processamento geométrico de precisão...")
        mascara_braco, pt_cotovelo, pt_punho = processar_fallback_close_up(img)
        
        if mascara_braco is not None:
            img_exibicao = segmentar_areas_antibraco(img_exibicao, pt_cotovelo, pt_punho, px_por_mm, mascara_braco, "Close-Up")
        else:
            print("❌ Não foi possível isolar o antebraço.")
    else:
        print(f"✅ Identificado(s) {len(bracos)} braço(s) via IA! Processando...")
        for braco in bracos:
            pt_cotovelo = braco["cotovelo"]
            pt_punho = braco["punho"]
            lado = braco["lado"]

            mascara_braco = isolar_mascara_antibraco(mascara_pessoa, pt_cotovelo, pt_punho, img.shape)
            img_exibicao = segmentar_areas_antibraco(img_exibicao, pt_cotovelo, pt_punho, px_por_mm, mascara_braco, lado)

    # 3. Exibição
    h_orig, w_orig = img_exibicao.shape[:2]
    altura_desejada = 850
    fator_escala = altura_desejada / float(h_orig)
    largura_desejada = int(w_orig * fator_escala)

    cv2.namedWindow("Segmentacao Antebraco - Robusta", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Segmentacao Antebraco - Robusta", largura_desejada, altura_desejada)
    cv2.imshow("Segmentacao Antebraco - Robusta", img_exibicao)
    print("\n👉 Pressione qualquer tecla na janela aberta para encerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("imagem", help="Caminho para o arquivo de imagem")
    parser.add_argument("--diametro-mm", type=float, default=19.0, help="Diâmetro do marcador verde em mm")
    args = parser.parse_args()

    main(args.imagem, args.diametro_mm)