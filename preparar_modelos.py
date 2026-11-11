"""Baixa explicitamente os pesos oficiais necessários ao aplicativo local."""
import argparse
import os
from pathlib import Path

MODELOS = ('yolov8n-pose.pt','yolo11x-pose.pt','yolo11x-seg.pt')


def main() -> None:
    """Verifica ou prepara modelos no diretório do projeto, sem enviar fotos."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verificar',action='store_true',help='Somente informa quais pesos já existem, sem download')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    os.chdir(root)
    for name in MODELOS:
        if (root/name).is_file():
            print(name, 'disponível')
        elif args.verificar:
            print(name, 'ausente')
        else:
            from ultralytics import YOLO
            print('Preparando',name,flush=True)
            YOLO(name)
            if not (root/name).is_file():
                raise FileNotFoundError(f'Não foi possível obter {name}. Confira a conexão e a instalação do Ultralytics.')
    print('As dimensões físicas dos marcadores devem ser conferidas nas fotos reais.')


if __name__=='__main__':
    main()
