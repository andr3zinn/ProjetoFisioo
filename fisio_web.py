"""Servidor da interface web local; usa apenas a biblioteca padrão do Python."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import hashlib
import json
import os
import sys
from pathlib import Path
import secrets
import socket
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import webbrowser
import zipfile

import cv2

from fisio_pipeline import ler_imagem, calibrar
from fisio_servico import Servico, reduzir, parametros, exportar

STATIC = Path(__file__).resolve().parent / 'web'
ROOT = STATIC.parent
APP_ID = 'projeto-fisio-local'


def versao_codigo() -> str:
    """Identifica o conjunto de arquivos que precisa estar carregado pelo serviço."""
    digest = hashlib.sha256()
    for name in ['fisio_web.py', 'fisio_pipeline.py', 'fisio_servico.py', 'fisio_visual.py', 'web/app.js', 'web/index.html', 'web/app.css']:
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()[:12]


def biblioteca() -> dict[str, Path]:
    """Lista somente fotos da pasta Imagens do projeto, sem aceitar caminhos externos."""
    return {p.name: p for p in (ROOT/'Imagens').iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.heic','.heif'}}


class Servidor(ThreadingHTTPServer):
    """Mantém fotos temporárias e serializa inferência para limitar uso de CPU."""
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self) -> None:
        """Evita que dois processos reutilizem a mesma porta no Windows."""
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, port: int) -> None:
        super().__init__(('127.0.0.1', port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.versao = versao_codigo()
        self.temp = tempfile.TemporaryDirectory(prefix='fisio_web_')
        self.sessions: dict = {}
        self.service = Servico()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()

    def server_close(self) -> None:
        """Espera a inferência terminar antes de limpar os arquivos da sessão."""
        super().server_close()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True)
        if hasattr(self, 'temp'):
            self.temp.cleanup()


class Handler(BaseHTTPRequestHandler):
    """Serve somente arquivos declarados e operações autenticadas pela sessão local."""
    server: Servidor

    def log_message(self, format: str, *args) -> None:
        """Evita registrar nomes e conteúdo de fotos no console."""

    def send(self, status: int, data: bytes, mime: str, attachment: bool = False) -> None:
        """Envia respostas sem cache e com restrições de carregamento de recursos."""
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="medicao-fisio.zip"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, status: int, data: dict) -> None:
        """Serializa apenas números finitos para consumo pelo navegador."""
        self.send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')

    def valid_host(self) -> bool:
        """Restringe o servidor ao endereço de loopback usado pela aplicação."""
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self) -> None:
        """Entrega interface, prévias e downloads de sessões da instância atual."""
        if not self.valid_host():
            self.json(403, {'error': 'Endereço local inválido.'})
            return
        parts = urlsplit(self.path).path.strip('/').split('/')
        route = '/'.join(parts)
        if route in {'', 'app.css', 'app.js'}:
            path = STATIC / (route or 'index.html')
            self.send(200, path.read_bytes(), {'': 'text/html; charset=utf-8', 'app.css': 'text/css; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8'}[route])
        elif route == 'api/config':
            self.json(200, {'token': self.server.token, 'app': APP_ID, 'versao': self.server.versao,
                'atualizado': self.server.versao == versao_codigo(), 'python': sys.executable,
                'pid': os.getpid(), 'pasta': str(ROOT), 'imagens': list(biblioteca())})
        elif len(parts) >= 3 and parts[0] == 'api' and parts[2] in self.server.sessions:
            session = self.server.sessions[parts[2]]
            if parts[1] == 'status':
                self.json(200, {k: session.get(k) for k in ['state', 'report', 'error', 'error_code', 'name', 'width', 'height']})
            elif parts[1] == 'image':
                image = session['preview'] if len(parts) == 3 else None
                if len(parts) == 4 and parts[3].isdigit() and int(parts[3]) < len(session.get('images', [])):
                    image = session['images'][int(parts[3])]
                if image is None:
                    self.json(404, {'error': 'Imagem indisponível.'})
                else:
                    ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    self.send(200, encoded.tobytes(), 'image/jpeg') if ok else self.json(500, {'error': 'Falha ao gerar prévia.'})
            elif parts[1] == 'export' and session.get('report') and session['state'] != 'running':
                folder = exportar(session['report'], session['images'], Path(self.server.temp.name))
                output = io.BytesIO()
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for file in folder.iterdir():
                        archive.write(file, file.name)
                self.send(200, output.getvalue(), 'application/zip', True)
            else:
                self.json(404, {'error': 'Recurso indisponível.'})
        else:
            self.json(404, {'error': 'Recurso não encontrado.'})

    def do_POST(self) -> None:
        """Valida a origem, limita uploads e agenda o processamento sem bloquear a UI."""
        origin = self.headers.get('Origin')
        valid_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if not self.valid_host() or (origin and origin not in valid_origins) or not secrets.compare_digest(self.headers.get('X-Fisio-Token', ''), self.server.token):
            # No Windows, fechar com corpo pendente pode descartar a própria resposta 403.
            try:
                pending = int(self.headers.get('Content-Length', '0'))
                if 0 < pending <= 8192:
                    self.rfile.read(pending)
            except ValueError:
                pass
            self.json(403, {'error': 'Sessão inválida. Atualize a página.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 30 * 1024 * 1024:
                self.json(413, {'error': 'Selecione um arquivo de até 30 MB.'})
                return
            route = urlsplit(self.path).path
            if route == '/api/release':
                body = json.loads(self.rfile.read(length))
                ident = body.get('id')
                session = self.server.sessions.get(ident)
                if session and session['state'] != 'running':
                    session['path'].unlink(missing_ok=True)
                    self.server.sessions.pop(ident, None)
                self.json(200, {'ok': True})
            elif route == '/api/library':
                body = json.loads(self.rfile.read(length))
                name = body.get('name')
                source = biblioteca().get(name)
                if source is None:
                    raise ValueError('Selecione uma foto da pasta Imagens pela lista.')
                self.prepare_upload(name, source.read_bytes())
            elif route == '/api/upload':
                if len(self.server.sessions) >= 12:
                    self.json(409, {'error': 'Limite desta sessão atingido. Reinicie a aplicação para liberar as fotos temporárias.'})
                    return
                name = Path(unquote(self.headers.get('X-Filename', 'foto.jpg')).replace('\\', '/')).name
                if Path(name).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.heic', '.heif'}:
                    raise ValueError('Use uma imagem JPG, PNG ou HEIC.')
                self.prepare_upload(name, self.rfile.read(length))
            elif route == '/api/analyze':
                if length > 8192:
                    raise ValueError('Parâmetros inválidos.')
                body = json.loads(self.rfile.read(length))
                session = self.server.sessions.get(body.get('id'))
                if session is None:
                    raise ValueError('Carregue a foto novamente.')
                args = parametros(body.get('method', 'circulo'), float(body.get('size', 19)), float(body.get('slice', 5)), int(body.get('markerId', 0)))
                points = body.get('points')
                tag_points = body.get('tagPoints')
                side = body.get('side', 'não informado')
                if side not in {'não informado', 'esquerdo', 'direito'}:
                    raise ValueError('Lado inválido.')
                if not self.server.lock.acquire(blocking=False):
                    self.json(409, {'error': 'Uma análise está em andamento. Aguarde sua conclusão.'})
                    return
                session.update(state='running', report=None, images=[], error=None, error_code=None)
                self.server.executor.submit(self.process, session, args, points, side, tag_points)
                self.json(202, {'state': 'running'})
            else:
                self.json(404, {'error': 'Operação não encontrada.'})
        except (ValueError, TypeError, OSError, cv2.error) as exc:
            self.json(400, {'error': str(exc)})

    def prepare_upload(self, name: str, content: bytes) -> None:
        """Cria cópia temporária; a liberação nunca remove a foto original da biblioteca."""
        if len(self.server.sessions) >= 12:
            self.json(409, {'error':'Limite de fotos abertas atingido. Troque a foto ou reinicie o aplicativo.'})
            return
        if len(content) > 30 * 1024 * 1024:
            raise ValueError('Use uma foto de até 30 MB.')
        ident = secrets.token_hex(16)
        path = Path(self.server.temp.name)/(ident+Path(name).suffix.lower())
        path.write_bytes(content)
        original = ler_imagem(path)
        img = reduzir(original)
        _, calibration, _ = calibrar(original, parametros())
        reference = None
        if calibration.get('metodo') == 'circulo':
            sx, sy = img.shape[1] / original.shape[1], img.shape[0] / original.shape[0]
            center, axes, angle = calibration['elipse']
            reference = dict(center=[center[0]*sx,center[1]*sy], axes=[axes[0]*sx,axes[1]*sy], angle=angle)
        self.server.sessions[ident] = dict(path=path,name=name,preview=img,width=img.shape[1],height=img.shape[0],state='ready',report=None,images=[])
        self.json(200,dict(id=ident,name=name,width=img.shape[1],height=img.shape[0],reference=reference))

    def process(self, session: dict, args: argparse.Namespace, points: list | None, side: str, tag_points: list | None = None) -> None:
        """Processa sequencialmente e converte falhas em estado consultável pela UI."""
        try:
            report, images = self.server.service.analisar(session['path'], args, points, side, tag_points)
            report['imagem'] = session['name']
            session.update(report=report, images=images, state='done')
        except Exception as exc:
            code = 'DIAMETRO_TAG_INCOMPATIVEL' if str(exc).startswith('DIAMETRO_TAG_INCOMPATIVEL:') else 'ANALISE_FALHOU'
            session.update(state='error', error=str(exc), error_code=code)
        finally:
            self.server.lock.release()


def main() -> None:
    """Inicia aplicação somente em localhost e abre o navegador padrão."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--porta', type=int, default=8765)
    parser.add_argument('--sem-abrir', action='store_true')
    args = parser.parse_args()
    from urllib.request import build_opener, ProxyHandler
    opener = build_opener(ProxyHandler({}))
    server = None
    for port in range(args.porta, min(args.porta + 20, 65536)):
        try:
            server = Servidor(port)
            break
        except OSError:
            try:
                with opener.open(f'http://127.0.0.1:{port}/api/config',timeout=2) as response:
                    running = json.load(response)
                if running.get('app') == APP_ID and running.get('versao') == versao_codigo() and running.get('atualizado'):
                    url = f'http://127.0.0.1:{port}'
                    print(f'Fisio atualizado já está ativo: {url}',flush=True)
                    if not args.sem_abrir:
                        webbrowser.open(url)
                    return
            except Exception:
                pass
    if server is None:
        raise RuntimeError('Não foi possível iniciar o serviço local em uma porta livre.')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Fisio {server.versao} disponível em {url}', flush=True)
    if not args.sem_abrir:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
