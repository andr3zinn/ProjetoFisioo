"""Serviço local reutilizável pela interface, sem depender de componentes visuais."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from fisio_pipeline import Detector, calibrar, ler_imagem, medir

ROOT = Path(__file__).resolve().parent


def parametros(metodo: str = 'circulo', tamanho_mm: float = 19., fatia_cm: float = 5., aruco_id: int = 0) -> argparse.Namespace:
    """Monta parâmetros validados para o serviço e para os modelos locais."""
    if metodo not in {'circulo', 'aruco'} or not np.isfinite([tamanho_mm, fatia_cm]).all() or not 1 <= tamanho_mm <= 200 or not .5 <= fatia_cm <= 20 or not 0 <= aruco_id < 50:
        raise ValueError('Confira o tamanho do marcador, a fatia e o ID ArUco.')
    return argparse.Namespace(calibracao=metodo, diametro_mm=tamanho_mm, aruco_mm=tamanho_mm,
        aruco_id=aruco_id, hsv_min=[35, 60, 40], hsv_max=[100, 255, 255], razao_eixos=.9,
        fatia_mm=fatia_cm * 10, largura=.6, kp_min=.5, device='cpu', imgsz=640,
        pose=str(ROOT / 'yolov8n-pose.pt'), seg=str(ROOT / 'yolo11x-seg.pt'),
        pose_fallback=str(ROOT / 'yolo11x-pose.pt'))


def reduzir(img: np.ndarray) -> np.ndarray:
    """Limita processamento a 1600 px no maior lado para conter memória em CPU."""
    scale = min(1., 1600 / max(img.shape[:2]))
    return cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img.copy()


class Servico:
    """Reutiliza modelos entre análises; chamadas devem ser serializadas pela interface."""
    def __init__(self) -> None:
        self.detector: Detector | None = None

    def analisar(self, path: Path, args: argparse.Namespace, pontos: list[list[float]] | None = None, lado: str = 'não informado', tag_pontos: list[list[float]] | None = None) -> tuple[dict, list[np.ndarray]]:
        """Calibra na foto original e mede em resolução limitada, preservando a métrica."""
        original = ler_imagem(path)
        h, calibration, flags = calibrar(original, args)
        img = reduzir(original)
        if tag_pontos is not None:
            if args.calibracao != 'circulo':
                raise ValueError('A calibração manual de diâmetro exige o modo círculo.')
            p = np.asarray(tag_pontos, dtype=float)
            if p.shape != (2, 2) or not np.isfinite(p).all() or np.any(p < 0) or np.any(p >= [img.shape[1], img.shape[0]]):
                raise ValueError('Marque dois extremos do diâmetro dentro da foto.')
            original_p = p * [original.shape[1] / img.shape[1], original.shape[0] / img.shape[0]]
            diameter = float(np.linalg.norm(original_p[1] - original_p[0]))
            if np.linalg.norm(p[1] - p[0]) < 8:
                raise ValueError('O marcador ficou pequeno demais. Amplie a captura ou marque um diâmetro maior.')
            if h is not None and calibration.get('metodo') == 'circulo':
                detected = float(np.sqrt(np.prod(calibration['elipse'][1])))
                if not .55 <= diameter / detected <= 1.8:
                    raise ValueError('DIAMETRO_TAG_INCOMPATIVEL: A linha marcada não corresponde ao diâmetro da tag detectada. Marque somente duas bordas opostas do adesivo, não cotovelo e punho, ou use a tag automática.')
            scale = diameter / args.diametro_mm
            h = np.diag([1 / scale, 1 / scale, 1.])
            calibration = dict(metodo='circulo', origem='manual', px_por_mm=scale,
                pontos_diametro_processados=p.tolist(), elipse=[original_p.mean(axis=0).tolist(), [diameter, diameter], 0.])
            flags = ['CALIBRACAO_MANUAL_DIAMETRO', 'PERSPECTIVA_NAO_CORRIGIDA', 'PLANO_COPLANAR_NAO_VERIFICADO']
        report: dict[str, Any] = dict(imagem=path.name, data=datetime.now().isoformat(timespec='seconds'),
            tipo_medida='area_projetada_2d', status='rejeitada', calibracao=calibration, flags=flags,
            resolucao_original=[original.shape[1], original.shape[0]], resolucao_processada=[img.shape[1], img.shape[0]],
            parametros={k: v for k, v in vars(args).items() if k not in {'pose', 'seg', 'pose_fallback'}}, bracos=[])
        if h is None:
            report.update(etapa='calibracao', acao_necessaria='calibrar_marcador')
            return report, []
        conversion = np.diag([original.shape[1] / img.shape[1], original.shape[0] / img.shape[0], 1.])
        h = h @ conversion
        report['calibracao']['homografia_processada_mm'] = h.tolist()
        report['modelo_validado_com_referencia'] = False
        if calibration['metodo'] == 'circulo':
            calibration['diametro_real_mm_informado'] = args.diametro_mm
            calibration['pixels_por_cm2_original'] = float((calibration['px_por_mm'] * 10) ** 2)
            calibration['pixels_por_cm2_processada'] = float(100 / abs(np.linalg.det(h[:2, :2])))
        if img.shape != original.shape:
            flags.append('IMAGEM_REDUZIDA_PARA_PROCESSAMENTO')
        del original
        if pontos is not None:
            p = np.asarray(pontos, dtype=float)
            if p.shape != (2, 2) or not np.isfinite(p).all() or np.any(p < 0) or np.any(p >= [img.shape[1], img.shape[0]]):
                raise ValueError('Marque cotovelo e punho dentro da foto.')
            arms = [dict(cotovelo=p[0], punho=p[1], lado=lado, pessoa=np.ones(img.shape[:2], bool))]
            flags.append('PONTOS_MANUAIS_SEM_MASCARA_PESSOA')
        else:
            if self.detector is None:
                self.detector = Detector(args)
            arms, detection_flags = self.detector.detectar(img)
            flags.extend(detection_flags)
        images = []
        for arm in arms:
            try:
                result, overlay = medir(img, arm, h, args)
                result['cotovelo_px'] = np.asarray(arm['cotovelo']).tolist()
                result['punho_px'] = np.asarray(arm['punho']).tolist()
                result['modelo_pose'] = arm.get('modelo_pose')
                result['modo'] = 'manual' if pontos is not None else 'automatico'
                if calibration['metodo'] == 'circulo':
                    ellipse = calibration['elipse']
                    center = (np.asarray(ellipse[0]) / np.diag(conversion)[:2]).astype(int)
                    axes = (np.asarray(ellipse[1]) / np.diag(conversion)[:2] / 2).astype(int)
                    cv2.ellipse(overlay, tuple(center), tuple(axes), ellipse[2], 0, 360, (0, 230, 255), 3)
                    cv2.putText(overlay, f'TAG {args.diametro_mm:g} mm', (max(0, center[0] - 60), max(20, center[1] - axes.max() - 8)), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 160, 255), 2, cv2.LINE_AA)
                report['bracos'].append(result)
                images.append(overlay)
            except ValueError as exc:
                flags.append(str(exc))
        if images:
            report['status'] = 'revisao_obrigatoria'
            report.update(etapa='concluida', acao_necessaria='revisar_resultado')
        else:
            flags.append('NENHUM_BRACO_MENSURAVEL')
            report.update(etapa='pose' if not arms else 'segmentacao', acao_necessaria='marcar_braco')
        return report, images


def exportar(report: dict, images: list[np.ndarray], destino: Path) -> Path:
    """Cria pasta exclusiva e exporta JSON, CSV e sobreposições sem sobrescrever."""
    import uuid
    folder = destino / ('medicao_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'resultado.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    with (folder / 'areas.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['imagem', 'braco', 'lado', 'fatia', 'inicio_cm', 'fim_cm', 'area_cm2_provisoria', 'area_total_cm2_provisoria', 'area_pixels', 'qualidade', 'flags'])
        for i, arm in enumerate(report['bracos']):
            for s in arm['fatias']:
                writer.writerow([report['imagem'], i + 1, arm['lado'], s['indice'], s['inicio_cm'], s['fim_cm'], s['area_cm2'], arm['area_total_cm2'], s.get('area_pixels'), arm.get('qualidade', 'provisoria'), '|'.join(report['flags'] + arm['flags'])])
        if not report['bracos']:
            writer.writerow([report['imagem'], '', '', '', '', '', '', '', '', 'rejeitada', '|'.join(report['flags'])])
    for i, img in enumerate(images):
        ok, data = cv2.imencode('.png', img)
        if not ok:
            raise OSError('Não foi possível salvar a imagem.')
        (folder / f'braco_{i + 1}.png').write_bytes(data.tobytes())
    return folder
