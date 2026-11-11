"""Medição experimental de área projetada; não estima superfície 3D ou volume."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from PIL import Image, ImageOps


def ler_imagem(path: Path) -> np.ndarray:
    """Lê RGB/HEIC aplicando orientação EXIF antes das coordenadas manuais."""
    if path.suffix.lower() in {'.heic', '.heif'}:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    with Image.open(path) as image:
        return cv2.cvtColor(np.array(ImageOps.exif_transpose(image).convert('RGB')), cv2.COLOR_RGB2BGR)


def calibrar(img: np.ndarray, args: argparse.Namespace) -> tuple[np.ndarray | None, dict, list[str]]:
    """Retorna homografia imagem→mm; círculo inclinado/ambíguo é rejeitado."""
    if args.calibracao == 'aruco':
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(img)
        selected = [] if ids is None else [c.reshape(4, 2) for c, i in zip(corners, ids.ravel()) if i == args.aruco_id]
        if len(selected) != 1:
            return None, {}, ['ARUCO_AUSENTE_OU_AMBIGUO']
        c = selected[0].astype(np.float32)
        if min(np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1)) < 20:
            return None, {}, ['ARUCO_RESOLUCAO_BAIXA']
        size = args.aruco_mm
        h = cv2.getPerspectiveTransform(c, np.float32([[0, 0], [size, 0], [size, size], [0, size]]))
        return h, {'metodo': 'aruco', 'px_por_mm': None, 'cantos_px': c.tolist()}, ['PLANO_COPLANAR_NAO_VERIFICADO', 'DISTORCAO_LENTE_NAO_CORRIGIDA']
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(args.hsv_min), np.array(args.hsv_max))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    candidates = []
    for c in contours:
        area, perimeter = cv2.contourArea(c), cv2.arcLength(c, True)
        if len(c) < 5 or perimeter <= 0 or not 80 < area < img.shape[0] * img.shape[1] * .05:
            continue
        ellipse = cv2.fitEllipse(c)
        small, large = sorted(ellipse[1])
        # Perímetro bruto de fotos grandes amplifica serrilhado e ruído da borda.
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        hull_perimeter = cv2.arcLength(hull, True)
        if hull_area <= 0 or area / hull_area < .85:
            continue
        circularity = 4 * math.pi * area / hull_perimeter**2
        fill = area / (math.pi * small * large / 4)
        if small >= 20 and small / large >= args.razao_eixos and circularity >= .75 and .85 <= fill <= 1.15:
            candidates.append((ellipse, circularity, small / large))
    if len(candidates) != 1:
        return None, {'candidatos': len(candidates)}, ['TAG_AUSENTE_INCLINADA_OU_AMBIGUA']
    ellipse, circularity, ratio = candidates[0]
    scale = math.sqrt(ellipse[1][0] * ellipse[1][1]) / args.diametro_mm
    return np.diag([1 / scale, 1 / scale, 1.]), {'metodo': 'circulo', 'px_por_mm': scale, 'circularidade': circularity, 'razao_eixos': ratio, 'elipse': ellipse}, ['PERSPECTIVA_NAO_CORRIGIDA', 'PLANO_COPLANAR_NAO_VERIFICADO']


def transformar(points: np.ndarray, h: np.ndarray) -> np.ndarray:
    """Transforma coordenadas e rejeita a região próxima ao horizonte projetivo."""
    p = np.column_stack((points, np.ones(len(points)))) @ h.T
    if np.any(np.abs(p[:, 2]) < 1e-8) or np.any(p[:, 2] * p[0, 2] <= 0):
        raise ValueError('HOMOGRAFIA_FORA_DO_PLANO_UTIL')
    return p[:, :2] / p[:, 2:]


def pele(img: np.ndarray) -> np.ndarray:
    """Heurística de pele; precisa de validação por tom de pele e iluminação."""
    ycc = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return (cv2.inRange(ycc, (0, 133, 77), (255, 173, 127)) > 0) & (cv2.inRange(hsv, (0, 15, 40), (25, 255, 255)) > 0)


class Detector:
    """Carrega modelos locais uma única vez; não baixa pesos implicitamente."""
    def __init__(self, args: argparse.Namespace) -> None:
        from ultralytics import YOLO
        for path in (args.pose, args.seg):
            if not Path(path).is_file():
                raise FileNotFoundError(path)
        self.pose, self.seg, self.args = YOLO(args.pose), YOLO(args.seg), args
        self.pose_reserva = None

    def detectar(self, img: np.ndarray) -> tuple[list[dict], list[str]]:
        """Associa cada pose à pessoa com maior IoU de caixas, sem unir pessoas."""
        opts = dict(verbose=False, device=self.args.device, imgsz=self.args.imgsz)
        pose = self.pose(img, **opts)[0]
        seg = self.seg(img, retina_masks=True, **opts)[0]
        arms, flags = self.associar(pose, seg, img.shape[:2])
        for arm in arms:
            arm['modelo_pose'] = Path(self.args.pose).name
        reserve = getattr(self.args, 'pose_fallback', None)
        if not arms and reserve and Path(reserve).is_file() and seg.masks is not None:
            from ultralytics import YOLO
            if self.pose_reserva is None:
                self.pose_reserva = YOLO(reserve)
            pose = self.pose_reserva(img, **opts)[0]
            recovered, reserve_flags = self.associar(pose, seg, img.shape[:2])
            if recovered:
                for arm in recovered:
                    arm['modelo_pose'] = Path(reserve).name
                return recovered, ['POSE_MODELO_RESERVA_UTILIZADO'] + reserve_flags
            flags.extend(reserve_flags)
        return arms, list(dict.fromkeys(flags))

    def associar(self, pose: Any, seg: Any, shape: tuple[int, int]) -> tuple[list[dict], list[str]]:
        """Associa resultados na mesma resolução, reutilizando a segmentação na reserva."""
        arms, flags = [], []
        if pose.keypoints is None or seg.masks is None:
            return [], ['POSE_OU_PESSOA_AUSENTE']
        boxes = seg.boxes.xyxy.cpu().numpy()
        classes = seg.boxes.cls.cpu().numpy()
        for box, keypoints in zip(pose.boxes.xyxy.cpu().numpy(), pose.keypoints.data.cpu().numpy()):
            lo, hi = np.maximum(boxes[:, :2], box[:2]), np.minimum(boxes[:, 2:], box[2:])
            intersection = np.maximum(hi - lo, 0).prod(axis=1)
            iou = intersection / np.maximum((boxes[:, 2:] - boxes[:, :2]).prod(axis=1) + np.prod(box[2:] - box[:2]) - intersection, 1)
            iou[classes != 0] = 0
            j = int(iou.argmax())
            if iou[j] < .3:
                flags.append('ASSOCIACAO_PESSOA_FALHOU')
                continue
            mask = seg.masks.data[j].cpu().numpy() > .5
            if mask.shape != shape:
                raise ValueError('MASCARA_FORA_DA_RESOLUCAO_ORIGINAL')
            for side, e, w in [('esquerdo', 7, 9), ('direito', 8, 10)]:
                confidence = float(min(keypoints[e, 2], keypoints[w, 2]))
                if confidence < self.args.kp_min:
                    flags.append('KEYPOINTS_BAIXA_CONFIANCA_' + side.upper())
                    continue
                arms.append(dict(lado=side, cotovelo=keypoints[e, :2], punho=keypoints[w, :2], pessoa=mask, confianca_keypoints=confidence))
        return arms, flags


def medir(img: np.ndarray, arm: dict, h: np.ndarray, args: argparse.Namespace) -> tuple[dict, np.ndarray]:
    """Refina por pele, ajusta PCA métrica e integra células em fatias exclusivas."""
    flags = ['PELE_HEURISTICA', 'REVISAO_VISUAL_OBRIGATORIA', 'EIXO_RETO_APROXIMADO']
    e, w = np.array(arm['cotovelo'], float), np.array(arm['punho'], float)
    direction = w - e
    length = np.linalg.norm(direction)
    if length < 20:
        raise ValueError('EIXO_CURTO')
    if not np.isfinite([e, w]).all() or np.any(np.array([e, w]) < 0) or np.any(np.array([e, w]) >= [img.shape[1], img.shape[0]]):
        raise ValueError('PONTOS_FORA_DA_IMAGEM')
    direction /= length
    yy, xx = np.indices(img.shape[:2])
    t = (xx - e[0]) * direction[0] + (yy - e[1]) * direction[1]
    n = -(xx - e[0]) * direction[1] + (yy - e[1]) * direction[0]
    roi = (t >= 0) & (t <= length) & (np.abs(n) < args.largura * length / 2)
    mask = (roi & arm['pessoa'] & pele(img)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        raise ValueError('MASCARA_VAZIA')
    j = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    if stats[j, cv2.CC_STAT_AREA] / max(mask.sum(), 1) < .9:
        flags.append('MASCARA_FRAGMENTADA')
    mask = labels == j
    if np.count_nonzero(mask & (np.abs(n) > args.largura * length / 2 - 2)) > 5:
        flags.append('MASCARA_LIMITADA_PELO_CORREDOR')
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        flags.append('MASCARA_NA_BORDA')
    y, x = np.nonzero(mask)
    if len(x) < 50:
        raise ValueError('MASCARA_INSUFICIENTE')
    points = np.column_stack((x, y)).astype(float)
    metric = transformar(points, h)
    ends = transformar(np.array([e, w]), h)
    values, vectors = np.linalg.eigh(np.cov(metric.T))
    axis = vectors[:, -1]
    if axis @ (ends[1] - ends[0]) < 0:
        axis = -axis
    angle = math.degrees(math.acos(float(np.clip(axis @ ((ends[1] - ends[0]) / np.linalg.norm(ends[1] - ends[0])), -1, 1))))
    if angle > 20 or values[-1] / max(values[0], 1e-9) < 3:
        flags.append('EIXO_PCA_INCERTO')
    distance = (metric - ends[0]) @ axis
    end = float((ends[1] - ends[0]) @ axis)
    if end <= 0:
        raise ValueError('EIXO_METRICO_INVALIDO')
    # Área exata dos quadriláteros de cada pixel no plano do marcador.
    corners = np.stack([transformar(points + offset, h) for offset in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]], axis=1)
    areas = .5 * np.abs(np.sum(corners[:, :, 0] * np.roll(corners[:, :, 1], -1, axis=1) - corners[:, :, 1] * np.roll(corners[:, :, 0], -1, axis=1), axis=1)) / 100
    valid = (distance >= 0) & (distance <= end)
    bins = np.floor(distance[valid] / args.fatia_mm).astype(int)
    number = max(1, math.ceil(end / args.fatia_mm))
    bins = np.minimum(bins, number - 1)
    sums = np.bincount(bins, weights=areas[valid], minlength=number)
    counts = np.bincount(bins, minlength=number)
    slices = []
    overlay = img.copy()
    colors = np.array([(40, 160, 240), (80, 210, 70), (200, 70, 180)], np.uint8)
    overlay[y[valid], x[valid]] = colors[bins % 3]
    overlay = cv2.addWeighted(img, .55, overlay, .45, 0)
    for i, area in enumerate(sums):
        section_mask = np.zeros(mask.shape, np.uint8)
        selected = bins == i
        section_mask[y[valid][selected], x[valid][selected]] = 255
        contours, _ = cv2.findContours(section_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        polygons = [cv2.approxPolyDP(c, 1., True).reshape(-1, 2).tolist() for c in contours]
        cv2.drawContours(overlay, contours, -1, (255, 255, 255), 2)
        slices.append(dict(indice=i + 1, inicio_cm=i * args.fatia_mm / 10,
            fim_cm=min((i + 1) * args.fatia_mm, end) / 10, area_cm2=float(area),
            area_pixels=int(counts[i]), contornos_px=polygons))
    coverage = float(np.ptp(distance[valid]) / end) if valid.any() else 0.
    if coverage < .8 or np.any(counts == 0):
        flags.append('COBERTURA_LONGITUDINAL_INSUFICIENTE')
    blocking = {'COBERTURA_LONGITUDINAL_INSUFICIENTE', 'MASCARA_LIMITADA_PELO_CORREDOR', 'MASCARA_NA_BORDA', 'EIXO_PCA_INCERTO', 'MASCARA_FRAGMENTADA'}
    result = dict(lado=arm['lado'], confianca_keypoints=arm.get('confianca_keypoints'), eixo_pca=axis.tolist(),
        angulo_ajuste_graus=angle, comprimento_cm=end / 10, cobertura_longitudinal=coverage,
        area_pixels=int(valid.sum()), area_total_cm2=float(sums.sum()), fatias=slices, flags=flags,
        qualidade='bloqueada' if blocking.intersection(flags) else 'provisoria',
        cotovelo_px=e.tolist(), punho_px=w.tolist(),
        origem_eixo_mm=ends[0].tolist())
    from fisio_visual import anotar_secoes
    return result, anotar_secoes(overlay, result, h)


def main() -> None:
    """Processa arquivo/pasta; erros individuais são registrados e o lote continua."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('entrada', type=Path)
    p.add_argument('--saida', type=Path, default=Path('resultados_fisio'))
    p.add_argument('--calibracao', choices=['circulo', 'aruco'], default='circulo')
    p.add_argument('--diametro-mm', type=float, default=19)
    p.add_argument('--aruco-mm', type=float, default=40)
    p.add_argument('--aruco-id', type=int, default=0)
    p.add_argument('--hsv-min', nargs=3, type=int, default=[35, 60, 40])
    p.add_argument('--hsv-max', nargs=3, type=int, default=[100, 255, 255])
    p.add_argument('--razao-eixos', type=float, default=.9)
    p.add_argument('--fatia-mm', type=float, default=50)
    p.add_argument('--largura', type=float, default=.6, help='Largura total do corredor / comprimento')
    p.add_argument('--kp-min', type=float, default=.5)
    p.add_argument('--pose', default='yolov8n-pose.pt')
    p.add_argument('--seg', default='yolo11x-seg.pt')
    p.add_argument('--device', default='cpu')
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--pontos', type=Path, help='JSON de pontos manuais por nome de arquivo orientado por EXIF')
    a = p.parse_args()
    if min(a.diametro_mm, a.aruco_mm, a.fatia_mm, a.largura, a.imgsz) <= 0 or not 0 < a.razao_eixos <= 1 or not 0 <= a.kp_min <= 1:
        p.error('Dimensões positivas e limiares entre 0 e 1 são obrigatórios')
    if not a.entrada.exists():
        p.error('Entrada inexistente')
    a.saida.mkdir(parents=True, exist_ok=True)
    manual = json.loads(a.pontos.read_text(encoding='utf-8')) if a.pontos else {}
    detector = None
    paths = [a.entrada] if a.entrada.is_file() else sorted(f for f in a.entrada.iterdir() if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.heic', '.heif'})
    records, rows = [], []
    for path in paths:
        record: dict[str, Any] = dict(imagem=str(path.resolve()), status='rejeitada', flags=[], bracos=[])
        try:
            img = ler_imagem(path)
            h, calibration, flags = calibrar(img, a)
            record.update(calibracao=calibration, flags=flags)
            if h is not None:
                record['calibracao']['homografia_imagem_mm'] = h.tolist()
                if path.name in manual:
                    arms = [dict(item, pessoa=np.ones(img.shape[:2], bool)) for item in manual[path.name]]
                    record['flags'].append('PONTOS_MANUAIS_SEM_MASCARA_PESSOA')
                else:
                    if detector is None:
                        detector = Detector(a)
                    arms, pose_flags = detector.detectar(img)
                    record['flags'].extend(pose_flags)
                for index, arm in enumerate(arms):
                    try:
                        result, overlay = medir(img, arm, h, a)
                        name = path.stem + '_' + hashlib.sha256(path.name.encode()).hexdigest()[:8] + f'_{index}.png'
                        if not cv2.imwrite(str(a.saida / name), overlay):
                            raise OSError('Falha ao salvar sobreposição')
                        result['sobreposicao'] = name
                        record['bracos'].append(result)
                    except Exception as exc:
                        record['flags'].append(f'BRACO_{index}: {type(exc).__name__}: {exc}')
                if record['bracos']:
                    record['status'] = 'revisao_obrigatoria'
                else:
                    record['flags'].append('NENHUM_BRACO_MENSURAVEL')
        except Exception as exc:
            record['flags'].append(f'{type(exc).__name__}: {exc}')
        records.append(record)
        for arm in record['bracos'] or [None]:
            for s in arm['fatias'] if arm else [None]:
                rows.append(dict(imagem=record['imagem'], status=record['status'], lado=arm['lado'] if arm else None, px_por_mm=record.get('calibracao', {}).get('px_por_mm'), area_total_cm2=arm['area_total_cm2'] if arm else None, confianca_keypoints=arm.get('confianca_keypoints') if arm else None, **(s or dict(indice=None, inicio_cm=None, fim_cm=None, area_cm2=None)), flags='|'.join(record['flags'] + (arm['flags'] if arm else []))))
        print(path.name, record['status'])
    output = dict(tipo_medida='area_projetada_no_plano_de_referencia', parametros={k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()}, imagens=records)
    (a.saida / 'resultados.json').write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (a.saida / 'resultados.csv').open('w', newline='', encoding='utf-8-sig') as f:
        fields = list(dict.fromkeys(k for row in rows for k in row)) if rows else ['imagem', 'status']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
