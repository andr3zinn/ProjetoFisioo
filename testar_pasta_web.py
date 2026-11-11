"""Exercita as 26 fotos pelo mesmo HTTP usado pela interface, sem cliques repetitivos."""
import json
from pathlib import Path
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from fisio_web import Servidor


def main() -> None:
    """Testa leitura, envio, calibração, inferência e prévias e salva resultados por arquivo."""
    server = Servidor(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    output = Path('teste_todas_imagens/http')
    output.mkdir(parents=True, exist_ok=True)
    results = []
    retries = []
    opener = build_opener(ProxyHandler({}))
    def call(route, body=None, headers=None):
        for attempt in range(2):
            try:
                with opener.open(Request(base+route,data=body,headers=headers or {}), timeout=120) as response:
                    return response.read()
            except (ConnectionError, OSError) as exc:
                if attempt or route == '/api/analyze':
                    raise
                retries.append(dict(rota=route.split('/')[2], erro=str(exc)))
                time.sleep(.3)
    headers = {'X-Fisio-Token':server.token,'Content-Type':'application/json'}
    try:
        for path in sorted(Path('Imagens').iterdir()):
            if path.suffix.lower() not in {'.jpg','.jpeg','.png','.heic','.heif'}:
                continue
            ident = None
            try:
                from urllib.parse import quote
                upload = json.loads(call('/api/upload',path.read_bytes(),dict(headers, **{'X-Filename':quote(path.name), 'Content-Type':'application/octet-stream'})))
                ident = upload['id']
                assert call('/api/image/'+ident)[:2] == b'\xff\xd8'
                call('/api/analyze',json.dumps(dict(id=ident)).encode(),headers)
                deadline = time.monotonic()+180
                while True:
                    result = json.loads(call('/api/status/'+ident))
                    if result['state'] != 'running':
                        break
                    if time.monotonic()>deadline:
                        raise TimeoutError('Inferência excedeu 180 segundos')
                    time.sleep(.15)
                result['upload_ok'] = True
                for index, arm in enumerate((result.get('report') or {}).get('bracos',[])):
                    image = call(f'/api/image/{ident}/{index}')
                    (output/f'{path.stem}_{index+1}.jpg').write_bytes(image)
            except Exception as exc:
                result = dict(name=path.name, state='error', error=str(exc))
            results.append(result)
            (output/'resultados.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
            (output/'conexoes_repetidas.json').write_text(json.dumps(retries,indent=2,ensure_ascii=False),encoding='utf-8')
            print(path.name, result['state'], len((result.get('report') or {}).get('bracos',[])),flush=True)
            if ident:
                call('/api/release',json.dumps(dict(id=ident)).encode(),headers)
        (output/'resultados.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__ == '__main__':
    main()
