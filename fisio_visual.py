"""Desenha limites métricos e legenda auditável, sem alterar pixels medidos."""
import cv2
import numpy as np


def anotar_secoes(img: np.ndarray, result: dict, h: np.ndarray) -> np.ndarray:
    """Adiciona linhas de corte e legenda fora da foto para não cobrir o braço."""
    height, width = img.shape[:2]
    panel = 440
    output = cv2.copyMakeBorder(img, 0, max(0, 220 + len(result['fatias']) * 85 - height), 0, panel, cv2.BORDER_CONSTANT, value=(244, 248, 245))
    scale = max(.45, min(.8, width / 1600))
    def label(text: str, x: int, y: int, color=(48, 78, 60), size=scale) -> None:
        cv2.putText(output, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)
    label('SECOES / AREA PROJETADA', width + 18, 34)
    label('BLOQUEADA - valores so para diagnostico' if result['qualidade'] == 'bloqueada' else 'Provisoria - conferir escala e limites', width + 18, 60, size=.45)
    e, w = np.asarray(result['cotovelo_px']), np.asarray(result['punho_px'])
    for point, text in [(e, 'Cotovelo'), (w, 'Punho')]:
        p = tuple(np.round(point).astype(int))
        cv2.circle(output, p, 7, (25, 45, 30), -1)
        cv2.circle(output, p, 7, (255, 255, 255), 2)
        label(text, max(0, p[0] - 70), max(22, p[1] - 12), (255, 255, 255))
    axis = np.array(result['eixo_pca'])
    origin = np.array(result['origem_eixo_mm'])
    inverse = np.linalg.inv(h)
    for section in result['fatias']:
        i = section['indice']
        y = 115 + (i - 1) * 85
        label(f"S{i:02d}  {section['inicio_cm']:.1f}-{section['fim_cm']:.1f} cm", width + 18, y)
        label(f"{section['area_cm2']:.2f} cm2 | {section['area_pixels']} px", width + 18, y + 25, size=.5)
        # A normal do corte no plano da imagem é obtida da equação da reta métrica.
        for cm in [section['inicio_cm'], section['fim_cm']]:
            metric_line = np.array([axis[0], axis[1], -float(axis @ origin + cm * 10)])
            line = h.T @ metric_line
            a, b, c = line
            # Limita a linha ao contorno da seção, em vez de atravessar todo o fundo.
            contours = section['contornos_px']
            if contours:
                points = np.concatenate([np.array(p) for p in contours if p], axis=0)
                center_metric = origin + axis * cm * 10
                q = inverse @ np.r_[center_metric, 1.]
                if abs(q[2]) < 1e-9:
                    continue
                center = q[:2] / q[2]
                tangent = np.array([-b, a])
                tangent /= max(np.linalg.norm(tangent), 1e-9)
                extents = (points - center) @ tangent
                p1 = np.round(center + tangent * (extents.min() - 4)).astype(int)
                p2 = np.round(center + tangent * (extents.max() + 4)).astype(int)
                cv2.line(output, tuple(p1), tuple(p2), (20, 45, 30), 3, cv2.LINE_AA)
                cv2.line(output, tuple(p1), tuple(p2), (255, 255, 255), 1, cv2.LINE_AA)
        if section['contornos_px']:
            points = np.concatenate([np.array(p) for p in section['contornos_px'] if p])
            center = points.mean(axis=0).astype(int)
            cv2.putText(output, f'S{i:02d}', tuple(center), cv2.FONT_HERSHEY_SIMPLEX, .65, (20, 30, 20), 4, cv2.LINE_AA)
            cv2.putText(output, f'S{i:02d}', tuple(center), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 1, cv2.LINE_AA)
    label(f"Total: {result['area_total_cm2']:.2f} cm2", width + 18, 145 + len(result['fatias']) * 85)
    return output
