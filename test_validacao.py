"""Regressões para escala quadrática, contagens, limites e métricas independentes."""
from argparse import Namespace
import unittest
import numpy as np
from fisio_pipeline import medir
from validar_fisio import comparar


class ValidacaoTest(unittest.TestCase):
    def test_area_contagem_e_escala_quadratica(self) -> None:
        img = np.zeros((350, 350, 3), np.uint8)
        img[100:150, 50:250] = (100, 140, 190)
        arm = dict(cotovelo=[50, 125], punho=[250, 125], lado='teste', pessoa=np.ones(img.shape[:2], bool))
        a = Namespace(largura=1, fatia_mm=50)
        first, annotated = medir(img, arm, np.diag([.5, .5, 1]), a)
        second, _ = medir(img, arm, np.diag([1., 1., 1]), a)
        self.assertEqual(first['area_pixels'], 10000)
        self.assertEqual(sum(s['area_pixels'] for s in first['fatias']), 10000)
        self.assertAlmostEqual(first['area_total_cm2'], 25)
        self.assertAlmostEqual(second['area_total_cm2'], 100)
        self.assertEqual(first['qualidade'], 'provisoria')
        self.assertGreater(annotated.shape[1], img.shape[1])
        self.assertTrue(all(s['contornos_px'] for s in first['fatias']))

    def test_cobertura_ruim_bloqueia(self) -> None:
        img = np.zeros((350, 350, 3), np.uint8)
        img[100:150, 100:200] = (100, 140, 190)
        arm = dict(cotovelo=[50, 125], punho=[250, 125], lado='teste', pessoa=np.ones(img.shape[:2], bool))
        result, _ = medir(img, arm, np.eye(3), Namespace(largura=1, fatia_mm=50))
        self.assertEqual(result['qualidade'], 'bloqueada')
        self.assertIn('COBERTURA_LONGITUDINAL_INSUFICIENTE', result['flags'])

    def test_metricas_com_valores_conhecidos(self) -> None:
        records = [dict(imagem='a', bracos=[dict(area_total_cm2=12, lado='teste', qualidade='provisoria')]), dict(imagem='b', bracos=[dict(area_total_cm2=16, lado='teste', qualidade='bloqueada')])]
        refs = [dict(imagem='a', segmento=1, area_cm2=10), dict(imagem='b', segmento=1, area_cm2=20), dict(imagem='c', segmento=1, area_cm2=20)]
        result = comparar(records, refs)
        self.assertEqual(result['mae_cm2'], 3)
        self.assertEqual(result['vies_cm2'], -1)
        self.assertEqual(result['mape_percentual'], 20)
        self.assertEqual(len(result['referencias_sem_resultado']), 1)
        self.assertIsNone(comparar(records, [])['mae_cm2'])


if __name__ == '__main__':
    unittest.main()
