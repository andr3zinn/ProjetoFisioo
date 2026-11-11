"""Inspeciona candidatos verdes/ciano sem convertê-los automaticamente em escala."""
from pathlib import Path
import json
import cv2
import numpy as np
from fisio_pipeline import ler_imagem


def main() -> None:
    """Gera mosaico e atributos de todos os candidatos para revisão visual."""
    output = Path('teste_todas_imagens')
    output.mkdir(exist_ok=True)
    tiles, records = [], []
    for path in sorted(Path('Imagens').iterdir()):
        if path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.heic', '.heif'}:
            continue
        img = ler_imagem(path)
        scale = min(1, 1000 / max(img.shape[:2]))
        img = cv2.resize(img, (round(img.shape[1] * scale), round(img.shape[0] * scale)))
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (35, 40, 25), (105, 255, 255))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        candidates = []
        for c in contours:
            area, per = cv2.contourArea(c), cv2.arcLength(c, True)
            if len(c) < 5 or area < 30 or area > mask.size * .05 or per == 0:
                continue
            ellipse = cv2.fitEllipse(c)
            small, large = sorted(ellipse[1])
            circ = 4 * np.pi * area / per**2
            if small / large < .5 or circ < .4:
                continue
            inside = np.zeros(mask.shape, np.uint8)
            cv2.drawContours(inside, [c], -1, 255, -1)
            hue = float(np.median(hsv[:, :, 0][inside > 0]))
            candidates.append(dict(elipse=ellipse, circularidade=circ, razao=small/large, hue=hue))
            cv2.ellipse(img, ellipse, (0, 255, 255), 2)
        records.append(dict(imagem=path.name, candidatos=candidates))
        factor = min(280 / img.shape[1], 300 / img.shape[0])
        thumb = cv2.resize(img, (round(img.shape[1] * factor), round(img.shape[0] * factor)))
        tile = np.full((340, 300, 3), 245, np.uint8)
        x = (300-thumb.shape[1])//2
        tile[28:28+thumb.shape[0], x:x+thumb.shape[1]] = thumb
        cv2.putText(tile, path.name, (7, 20), cv2.FONT_HERSHEY_SIMPLEX, .42, (30, 30, 30), 1)
        cv2.putText(tile, f'Candidatos: {len(candidates)}', (7, 334), cv2.FONT_HERSHEY_SIMPLEX, .4, (30,30,30), 1)
        tiles.append(tile)
    while len(tiles)%4:
        tiles.append(np.full_like(tiles[0], 245))
    cv2.imwrite(str(output/'mosaico.jpg'), np.vstack([np.hstack(tiles[i:i+4]) for i in range(0,len(tiles),4)]))
    (output/'candidatos.json').write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
