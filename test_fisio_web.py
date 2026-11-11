"""Testes HTTP do envio, análise manual e download da aplicação local."""
import io
import json
import threading
import time
import unittest
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
import zipfile
import cv2
import numpy as np
from fisio_web import Servidor


class WebTest(unittest.TestCase):
    def test_porta_ocupada_nao_reutiliza_servico(self) -> None:
        with self.assertRaises(OSError):
            Servidor(self.server.server_port)
        self.assertIn(b'Uma medida mais clara', self.request('/'))
    def test_versao_e_biblioteca_nao_remove_original(self) -> None:
        from fisio_web import APP_ID, versao_codigo
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        health = json.loads(self.request('/api/config'))
        self.assertEqual(health['app'], APP_ID)
        self.assertEqual(health['versao'], versao_codigo())
        self.assertTrue(health['atualizado'])
        headers = {'X-Fisio-Token':self.server.token}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'foto_sintetica.png'
            cv2.imwrite(str(source),np.zeros((100,100,3),np.uint8))
            content=source.read_bytes()
            with patch('fisio_web.biblioteca',return_value={source.name:source}):
                result = json.loads(self.request('/api/library',json.dumps({'name':source.name}).encode(),headers))
                self.request('/api/release',json.dumps({'id':result['id']}).encode(),headers)
            self.assertEqual(source.read_bytes(),content)
        with self.assertRaises(HTTPError):
            self.request('/api/library',json.dumps({'name':'../fisio_web.py'}).encode(),headers)
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = Servidor(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def request(self, route, body=None, headers=None):
        req = Request(self.url + route, data=body, headers=headers or {})
        with build_opener(ProxyHandler({})).open(req, timeout=15) as response:
            return response.read()

    def test_upload_medicao_download(self) -> None:
        img = np.zeros((400, 400, 3), np.uint8)
        img[100:150, 50:250] = (100, 140, 190)
        cv2.circle(img, (320, 300), 38, (0, 255, 0), -1)
        data = cv2.imencode('.png', img)[1].tobytes()
        headers = {'X-Fisio-Token': self.server.token, 'X-Filename': 'foto.png'}
        upload = json.loads(self.request('/api/upload', data, headers))
        body = json.dumps(dict(id=upload['id'], points=[[50, 125], [250, 125]])).encode()
        self.request('/api/analyze', body, headers)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = json.loads(self.request('/api/status/' + upload['id']))
            if result['state'] != 'running':
                break
            time.sleep(.02)
        self.assertEqual(result['state'], 'done')
        self.assertEqual(result['report']['imagem'], 'foto.png')
        self.assertGreater(result['report']['bracos'][0]['area_total_cm2'], 0)
        with zipfile.ZipFile(io.BytesIO(self.request('/api/export/' + upload['id']))) as archive:
            self.assertEqual(set(archive.namelist()), {'resultado.json', 'areas.csv', 'braco_1.png'})

    def test_recusa_post_sem_token_e_origem_externa(self) -> None:
        for headers in [{}, {'X-Fisio-Token': self.server.token, 'Origin': 'https://exemplo.com'}]:
            with self.assertRaises(HTTPError) as error:
                self.request('/api/upload', b'imagem', headers)
            self.assertEqual(error.exception.code, 403)

    def test_interface_e_rotas_restritas(self) -> None:
        self.assertIn(b'Uma medida mais clara', self.request('/'))
        with self.assertRaises(HTTPError) as error:
            self.request('/fisio_servico.py')
        self.assertEqual(error.exception.code, 404)

    def test_trocar_mais_de_doze_fotos_libera_sessao(self) -> None:
        data = cv2.imencode('.png', np.zeros((100,100,3), np.uint8))[1].tobytes()
        headers = {'X-Fisio-Token':self.server.token,'X-Filename':'foto.png'}
        for _ in range(15):
            item = json.loads(self.request('/api/upload', data, headers))
            self.request('/api/release', json.dumps({'id':item['id']}).encode(), headers)
            self.assertNotIn(item['id'], self.server.sessions)


if __name__ == '__main__':
    unittest.main()
