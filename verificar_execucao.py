"""Diagnóstico do serviço local sem exibir tokens ou conteúdo das fotos."""
import json
from urllib.request import build_opener, ProxyHandler
from fisio_web import versao_codigo


def main() -> None:
    """Compara serviços em execução com a versão atual dos arquivos do projeto."""
    opener = build_opener(ProxyHandler({}))
    print('Versão dos arquivos:', versao_codigo(), flush=True)
    for port in range(8765,8770):
        try:
            with opener.open(f'http://127.0.0.1:{port}/api/config',timeout=1) as response:
                d = json.load(response)
            print(port, {k:d.get(k) for k in ['app','versao','atualizado','python','pasta','pid']},flush=True)
        except Exception as exc:
            print(port,type(exc).__name__,flush=True)


if __name__ == '__main__':
    main()
