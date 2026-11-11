"""Regressão real da foto relatada, sem confundir execução com validação clínica."""
import json
from pathlib import Path
import cv2
from fisio_servico import Servico, parametros


def main() -> None:
    """Reproduz a calibração confundida com eixo e confere a recuperação da pose."""
    path = Path('Imagens/IMG_8006.HEIC')
    output = Path('correcao_8006')
    output.mkdir(exist_ok=True)
    service = Servico()
    invalid = [[652.5490106320849,400.39212095971203],[762.3529322007123,1039.6078072342218]]
    try:
        service.analisar(path,parametros(),tag_pontos=invalid)
        raise AssertionError('Diâmetro incompatível foi aceito')
    except ValueError as exc:
        assert str(exc).startswith('DIAMETRO_TAG_INCOMPATIVEL:'), str(exc)
        invalid_message = str(exc)
    report, images = service.analisar(path,parametros())
    assert images and report['bracos'], report
    assert any(a['modelo_pose']=='yolo11x-pose.pt' for a in report['bracos'])
    for i, image in enumerate(images):
        cv2.imencode('.jpg',image)[1].tofile(str(output/f'automatico_{i+1}.jpg'))
    arm = report['bracos'][0]
    manual, manual_images = service.analisar(path,parametros(),[arm['cotovelo_px'],arm['punho_px']],arm['lado'])
    assert manual_images and manual['bracos'], manual
    result = dict(falha_reproduzida=invalid_message,automatico=report,confirmacao_dois_pontos=manual,
        observacao='Pontos do teste manual reaproveitam a proposta do modelo. Não são anotação clínica independente; não há área de referência.')
    (output/'regressao.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Calibração incompatível bloqueada; automático e manual produziram seções.')
    print([(a['modelo_pose'],a['qualidade'],len(a['fatias'])) for a in report['bracos']])


if __name__ == '__main__':
    main()
