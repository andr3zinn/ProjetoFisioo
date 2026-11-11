"""Testes geométricos sintéticos; não constituem validação clínica."""
import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from argparse import Namespace
import cv2
import numpy as np
from fisio_pipeline import calibrar, medir, transformar


class GeometriaTest(unittest.TestCase):
    def test_cli_exporta_medida_e_rejeicao(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            img = np.zeros((400, 400, 3), np.uint8)
            img[100:150, 50:250] = (100, 140, 190)
            cv2.circle(img, (320, 300), 38, (0, 255, 0), -1)
            cv2.imwrite(str(root / 'foto.png'), img)
            (root / 'falha.jpg').write_bytes(b'invalido')
            manual = root / 'pontos.json'
            manual.write_text(json.dumps({'foto.png': [dict(lado='teste', cotovelo=[50, 125], punho=[250, 125])]}))
            process = subprocess.run([sys.executable, str(Path(__file__).with_name('fisio_pipeline.py')), str(root), '--pontos', str(manual), '--saida', str(root / 'out')], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            data = json.loads((root / 'out' / 'resultados.json').read_text(encoding='utf-8'))
            self.assertEqual([r['status'] for r in data['imagens']], ['rejeitada', 'revisao_obrigatoria'])
            self.assertTrue((root / 'out' / 'resultados.csv').is_file())

    def test_circulo_e_ambiguidade(self) -> None:
        args = Namespace(calibracao='circulo', hsv_min=[35, 60, 40], hsv_max=[85, 255, 255], razao_eixos=.9, diametro_mm=19)
        img = np.zeros((400, 400, 3), np.uint8)
        cv2.circle(img, (100, 100), 38, (0, 255, 0), -1)
        h, info, _ = calibrar(img, args)
        self.assertIsNotNone(h)
        self.assertAlmostEqual(info['px_por_mm'], 4, delta=.1)
        cv2.circle(img, (300, 100), 38, (0, 255, 0), -1)
        self.assertIsNone(calibrar(img, args)[0])

    def test_retangulo_area_fatias_rotacao(self) -> None:
        args = Namespace(largura=1., fatia_mm=50)
        for vertical in (False, True):
            img = np.zeros((350, 350, 3), np.uint8)
            # RGB de pele controlado para testar geometria, não diversidade de pele.
            if vertical:
                img[50:250, 100:150] = (100, 140, 190)
                e, w = [125, 50], [125, 250]
            else:
                img[100:150, 50:250] = (100, 140, 190)
                e, w = [50, 125], [250, 125]
            arm = dict(cotovelo=e, punho=w, lado='teste', pessoa=np.ones(img.shape[:2], bool))
            result, _ = medir(img, arm, np.diag([.5, .5, 1]), args)
            self.assertAlmostEqual(result['area_total_cm2'], 25, places=5)
            self.assertEqual(len(result['fatias']), 2)
            self.assertAlmostEqual(sum(s['area_cm2'] for s in result['fatias']), 25)

    def test_homografia_e_horizonte(self) -> None:
        src = np.float32([[20, 20], [120, 30], [100, 150], [10, 120]])
        dst = np.float32([[0, 0], [40, 0], [40, 40], [0, 40]])
        h = cv2.getPerspectiveTransform(src, dst)
        np.testing.assert_allclose(transformar(src, h), dst, atol=1e-5)
        with self.assertRaises(ValueError):
            transformar(np.array([[0, 0], [2, 0]]), np.array([[1., 0, 0], [0, 1, 0], [1, 0, -1]]))


if __name__ == '__main__':
    unittest.main()
