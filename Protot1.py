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

def segmentar_pele(img):
    """ Segmenta a pele de forma bruta """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    
    inferior_hsv = np.array([0, 15, 40], dtype=np.uint8)
    superior_hsv = np.array([25, 160, 255], dtype=np.uint8)
    mascara_hsv = cv2.inRange(hsv, inferior_hsv, superior_hsv)
    
    inferior_ycrcb = np.array([0, 133, 77], dtype=np.uint8)
    superior_ycrcb = np.array([255, 173, 127], dtype=np.uint8)
    mascara_ycrcb = cv2.inRange(ycrcb, inferior_ycrcb, superior_ycrcb)
    
    mascara_pele = cv2.bitwise_and(mascara_hsv, mascara_ycrcb)
    return mascara_pele

def escrever_texto_com_contorno(img, texto, posicao, fonte, escala, cor, espessura, cor_borda=(0, 0, 0), espessura_borda=3):
    """ Desenha um texto nítido com bordas escuras """
    cv2.putText(img, texto, posicao, fonte, escala, cor_borda, espessura + espessura_borda, cv2.LINE_AA)
    cv2.putText(img, texto, posicao, fonte, escala, cor, espessura, cv2.LINE_AA)

def processar_antebraco_v5_final(caminho_imagem):
    img = carregar_imagem_universal(caminho_imagem)
    if img is None:
        print("Erro ao carregar a imagem.")
        return

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # --- 1. DETECÇÃO DA BOLINHA ---
    verde_inferior = np.array([75, 80, 50])
    verde_superior = np.array([105, 255, 255])
    mascara_adesivo = cv2.inRange(hsv, verde_inferior, verde_superior)

    kernel_adesivo = np.ones((5, 5), np.uint8)
    mascara_adesivo = cv2.morphologyEx(mascara_adesivo, cv2.MORPH_OPEN, kernel_adesivo)
    mascara_adesivo = cv2.morphologyEx(mascara_adesivo, cv2.MORPH_CLOSE, kernel_adesivo)

    contornos_adesivo, _ = cv2.findContours(mascara_adesivo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tem_adesivo = False
    escala_mm_px = 1.0

    if contornos_adesivo:
        maior_adesivo = max(contornos_adesivo, key=cv2.contourArea)
        if len(maior_adesivo) >= 5:
            elipse = cv2.fitEllipse(maior_adesivo)
            (cx_adesivo, cy_adesivo), (eixo_menor, eixo_maior), angulo_adesivo = elipse
            DIAMETRO_REAL_MM = 19.0
            escala_mm_px = DIAMETRO_REAL_MM / eixo_maior
            cx_adesivo, cy_adesivo = int(cx_adesivo), int(cy_adesivo)
            tem_adesivo = True
            
    if not tem_adesivo:
        print("Adesivo não detectado!")
        return

    # --- 2. ISOLAMENTO MORFOLÓGICO DO BRAÇO (Removendo a Perna/Fundo) ---
    mascara_pele = segmentar_pele(img)
    
    # Kernel dinâmico baseado na resolução da imagem para quebrar a ponte entre braço e perna
    k_size = int(img.shape[1] * 0.015) | 1  # Força ser ímpar
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
    
    pele_erodida = cv2.erode(mascara_pele, kernel_erode)
    contornos_erodidos, _ = cv2.findContours(pele_erodida, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    mascara_braco_limpa = np.zeros_like(mascara_pele)
    achou_braco = False
    
    for cnt in contornos_erodidos:
        temp_mask = np.zeros_like(pele_erodida)
        cv2.drawContours(temp_mask, [cnt], -1, 255, -1)
        dilated_temp = cv2.dilate(temp_mask, kernel_erode)
        
        # Verifica se esta parte separada contém o adesivo
        if dilated_temp[cy_adesivo, cx_adesivo] > 0:
            mascara_braco_limpa = cv2.bitwise_and(mascara_pele, dilated_temp)
            achou_braco = True
            break
            
    if not achou_braco:
        print("Falha ao isolar braço. Usando máscara total.")
        mascara_braco_limpa = mascara_pele

    # --- 3. MATEMÁTICA VETORIAL E BUSCA DO PULSO ---
    y_coords, x_coords = np.where(mascara_braco_limpa > 0)
    if len(x_coords) == 0: return
    
    pontos_xy = np.column_stack((x_coords, y_coords))
    [vx, vy, x0, y0] = cv2.fitLine(pontos_xy, cv2.DIST_L2, 0, 0.01, 0.01)
    vx, vy = float(vx[0]), float(vy[0])
    
    # Normalizar vetor do braço
    norm = math.hypot(vx, vy)
    vx, vy = vx/norm, vy/norm

    # Projeção T (Distância longitudinal da bolinha) e P (Largura lateral)
    T_vals = (x_coords - cx_adesivo) * vx + (y_coords - cy_adesivo) * vy
    P_vals = (x_coords - cx_adesivo) * (-vy) + (y_coords - cy_adesivo) * vx

    t_min, t_max = np.min(T_vals), np.max(T_vals)
    
    # Determinar a direção da mão (extremidade mais longa do vetor)
    if abs(t_max) > abs(t_min):
        t_extremo = t_max
        passo_dir = 1
    else:
        t_extremo = t_min
        passo_dir = -1

    # Escanear a largura do braço para achar o pulso (ponto mais estreito)
    T_ints = np.round(T_vals).astype(int)
    larguras = {}
    for t_idx in range(int(min(0, t_extremo)), int(max(0, t_extremo)) + 1):
        mask_t = (T_ints == t_idx)
        if np.any(mask_t):
            p_sub = P_vals[mask_t]
            larguras[t_idx] = np.max(p_sub) - np.min(p_sub)

    # Buscar o pulso na metade distal (mais afastada) do braço para evitar o cotovelo
    t_inicio_busca = int(t_extremo * 0.50)
    t_fim_busca = int(t_extremo * 0.90) # Ignorar as pontas dos dedos
    
    largura_minima = float('inf')
    t_pulso = t_extremo
    
    passo = 1 if t_extremo > 0 else -1
    for t_idx in range(t_inicio_busca, t_fim_busca, passo):
        if t_idx in larguras and larguras[t_idx] < largura_minima:
            largura_minima = larguras[t_idx]
            t_pulso = t_idx

    # --- 4. DIVISÃO ESTABELECIDA (BOLINHA -> PULSO) ---
    t_inicio_area = 0 # Centro do adesivo
    t_fim_area = t_pulso # Pulso exato
    passo_t = (t_fim_area - t_inicio_area) / 5.0

    overlay_cores = np.zeros_like(img)
    cores_areas = [(230, 216, 173), (180, 230, 180), (160, 220, 240), (140, 180, 240), (220, 160, 220)]
    
    dados_textos = []

    # Pintar as fatias utilizando arrays lógicos (sem retângulos que vazam)
    for i in range(5):
        t1 = t_inicio_area + i * passo_t
        t2 = t_inicio_area + (i + 1) * passo_t
        
        t_lower, t_upper = min(t1, t2), max(t1, t2)
        mask_fatia = (T_vals >= t_lower) & (T_vals <= t_upper)
        
        # Pinta estritamente os pixels que já pertencem à máscara limpa do braço
        overlay_cores[y_coords[mask_fatia], x_coords[mask_fatia]] = cores_areas[i]
        
        if np.any(mask_fatia):
            cx_txt = int(np.mean(x_coords[mask_fatia]))
            cy_txt = int(np.mean(y_coords[mask_fatia]))
            altura_cm = (abs(passo_t) * escala_mm_px) / 10.0
            dados_textos.append((cx_txt, cy_txt, f"Area {5-i}", f"{altura_cm:.1f} cm"))

    img_final = img.copy()
    cv2.addWeighted(overlay_cores, 0.45, img_final, 1.0, 0, img_final)

    # --- 5. RENDERIZAÇÃO EM HD ---
    altura_tela = 850
    escala_exib = altura_tela / img_final.shape[0]
    largura_tela = int(img_final.shape[1] * escala_exib)
    
    saida = cv2.resize(img_final, (largura_tela, altura_tela), interpolation=cv2.INTER_AREA)

    # Desenhar Bolinha
    elipse_redim = ((cx_adesivo * escala_exib, cy_adesivo * escala_exib), 
                    (eixo_menor * escala_exib, eixo_maior * escala_exib), angulo_adesivo)
    cv2.ellipse(saida, elipse_redim, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.circle(saida, (int(cx_adesivo * escala_exib), int(cy_adesivo * escala_exib)), 4, (0, 0, 255), -1)

    # Desenhar Linhas Divisórias contidas no braço
    for i in range(1, 5):
        t_div = t_inicio_area + i * passo_t
        t_int = int(round(t_div))
        
        if t_int in larguras:
            mask_t = (T_ints == t_int)
            p_max = np.max(P_vals[mask_t])
            p_min = np.min(P_vals[mask_t])
            
            x_p1 = int((cx_adesivo + t_div * vx + p_min * (-vy)) * escala_exib)
            y_p1 = int((cy_adesivo + t_div * vy + p_min * vx) * escala_exib)
            x_p2 = int((cx_adesivo + t_div * vx + p_max * (-vy)) * escala_exib)
            y_p2 = int((cy_adesivo + t_div * vy + p_max * vx) * escala_exib)
            
            cv2.line(saida, (x_p1, y_p1), (x_p2, y_p2), (40, 40, 40), 2, cv2.LINE_AA)

    # Desenhar Textos
    for cx, cy, lbl, sublbl in dados_textos:
        cxs, cys = int(cx * escala_exib), int(cy * escala_exib)
        escrever_texto_com_contorno(saida, lbl, (cxs - 35, cys - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        escrever_texto_com_contorno(saida, sublbl, (cxs - 30, cys + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 255, 220), 1)

    # Painel HUD
    hud_temp = saida.copy()
    cv2.rectangle(hud_temp, (10, 10), (380, 110), (15, 15, 15), -1)
    cv2.addWeighted(hud_temp, 0.75, saida, 0.25, 0, saida)
    cv2.rectangle(saida, (10, 10), (380, 110), (100, 100, 100), 1, cv2.LINE_AA)
    
    escrever_texto_com_contorno(saida, "MAPEAMENTO INTELIGENTE (PULSO DETECTADO)", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    escrever_texto_com_contorno(saida, f"Calibracao do Adesivo: {escala_mm_px:.4f} mm/px", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    escrever_texto_com_contorno(saida, f"Deteccao: Bolinha ate o Estreitamento do Pulso", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
    
    total_cm = (abs(t_fim_area - t_inicio_area) * escala_mm_px) / 10.0
    escrever_texto_com_contorno(saida, f"Distancia Mapeada (Ate o Pulso): {total_cm:.1f} cm", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 255, 100), 1)

    cv2.imshow("Mapeamento de Areas do Antebraco", saida)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

# Execute a V5 na sua imagem (lembre de checar o caminho do arquivo no seu PC)
processar_antebraco_v5_final(r'Imagens\IMG_8013.HEIC')