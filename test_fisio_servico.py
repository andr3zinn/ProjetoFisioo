"""Verifica a integração da interface com a métrica e a exportação."""
import json
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from fisio_servico import Servico, parametros, exportar


class ServicoTest(unittest.TestCase):
    def test_nao_confunde_eixo_braco_com_diametro_tag(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tag.png'
            img=np.zeros((400,400,3),np.uint8)
            cv2.circle(img,(320,300),38,(0,255,0),-1)
            cv2.imwrite(str(path),img)
            with self.assertRaisesRegex(ValueError,'DIAMETRO_TAG_INCOMPATIVEL'):
                Servico().analisar(path,parametros(),tag_pontos=[[60,30],[250,350]])

    def test_pose_ausente_pede_marcacao_e_preserva_calibracao(self) -> None:
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'closeup.png'
            img=np.zeros((400,400,3),np.uint8)
            img[100:150,50:250]=(100,140,190)
            cv2.circle(img,(320,300),38,(0,255,0),-1)
            cv2.imwrite(str(path),img)
            service=Servico()
            service.detector=SimpleNamespace(detectar=lambda img:([],['KEYPOINTS_BAIXA_CONFIANCA']))
            report,images=service.analisar(path,parametros())
            self.assertEqual(report['acao_necessaria'],'marcar_braco')
            self.assertIn('homografia_processada_mm',report['calibracao'])
            manual, images=service.analisar(path,parametros(),[[50,125],[250,125]])
            self.assertTrue(images)
            self.assertEqual(manual['bracos'][0]['modo'],'manual')
            self.assertEqual(manual['calibracao']['px_por_mm'],report['calibracao']['px_por_mm'])
    def test_tag_ciano_e_borda_irregular(self) -> None:
        from fisio_pipeline import calibrar
        img = np.zeros((800,800,3),np.uint8)
        angles = np.linspace(0,2*np.pi,600,endpoint=False)
        radius = 100+2*np.sin(angles*45)
        points = np.column_stack((400+radius*np.cos(angles),400+radius*np.sin(angles))).astype(np.int32)
        color = cv2.cvtColor(np.uint8([[[92,220,180]]]),cv2.COLOR_HSV2BGR)[0,0].tolist()
        cv2.fillPoly(img,[points],color)
        h, info, flags = calibrar(img,parametros())
        self.assertIsNotNone(h)
        self.assertAlmostEqual(info['px_por_mm'],200/19,delta=.2)
    def test_tag_manual_sem_cor_e_limites(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sem_verde.png'
            img = np.zeros((400, 400, 3), np.uint8)
            img[100:150, 50:250] = (100, 140, 190)
            cv2.imwrite(str(path), img)
            service = Servico()
            result, images = service.analisar(path, parametros(), [[50,125],[250,125]], 'esquerdo', [[300,300],[376,300]])
            self.assertEqual(result['calibracao']['px_por_mm'], 4)
            self.assertAlmostEqual(result['bracos'][0]['area_total_cm2'], 6.25)
            self.assertEqual(len(images), 1)
            with self.assertRaises(ValueError):
                service.analisar(path, parametros(), tag_pontos=[[10,10],[10,10]])
    def test_reducao_preserva_area_e_exportacao(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            img = np.zeros((2000, 2000, 3), np.uint8)
            img[750:1050, 400:1400] = (100, 140, 190)
            cv2.circle(img, (1700, 1700), 38, (0, 255, 0), -1)
            path = root / 'foto.png'
            cv2.imwrite(str(path), img)
            report, images = Servico().analisar(path, parametros(), [[320, 720], [1120, 720]], 'esquerdo')
            self.assertEqual(report['resolucao_processada'], [1600, 1600])
            self.assertEqual(report['status'], 'revisao_obrigatoria')
            expected = 300000 / (report['calibracao']['px_por_mm'] ** 2 * 100)
            self.assertAlmostEqual(report['bracos'][0]['area_total_cm2'], expected, delta=expected * .005)
            self.assertIsNone(Servico().detector)
            destination = exportar(report, images, root)
            self.assertTrue((destination / 'braco_1.png').is_file())
            saved = json.loads((destination / 'resultado.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['bracos'], report['bracos'])
            self.assertNotEqual(destination, exportar(report, images, root))

    def test_rejeicao_nao_carrega_modelos(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sem_tag.png'
            cv2.imwrite(str(path), np.zeros((400, 400, 3), np.uint8))
            service = Servico()
            report, images = service.analisar(path, parametros())
            self.assertEqual(report['status'], 'rejeitada')
            self.assertEqual(images, [])
            self.assertIsNone(service.detector)

    def test_parametros_invalidos(self) -> None:
        for size, slice_cm in [(0, 5), (19, 0), (float('nan'), 5)]:
            with self.assertRaises(ValueError):
                parametros(tamanho_mm=size, fatia_cm=slice_cm)


if __name__ == '__main__':
    unittest.main()
