"""Audita o lote e compara referências fornecidas, sem inferir verdade física das fotos."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from fisio_servico import Servico, parametros


def comparar(records: list[dict], referencias: list[dict]) -> dict:
    """Calcula erros somente de referências positivas com imagem/segmento correspondentes."""
    by_name = {r['imagem']: r for r in records}
    pairs, excluded = [], []
    for ref in referencias:
        value = ref.get('area_cm2')
        if value is None:
            continue
        if not np.isfinite(value) or value <= 0:
            raise ValueError('Áreas de referência devem ser positivas e finitas.')
        record = by_name.get(ref['imagem'])
        index = int(ref['segmento']) - 1
        if not record or index < 0 or index >= len(record.get('bracos', [])):
            excluded.append(dict(referencia=ref, motivo='sem_segmento_correspondente'))
            continue
        arm = record['bracos'][index]
        if ref.get('lado') and ref['lado'] != arm['lado']:
            excluded.append(dict(referencia=ref, motivo='lado_divergente'))
            continue
        estimate = arm['area_total_cm2']
        pairs.append(dict(imagem=ref['imagem'], segmento=index + 1, referencia_cm2=value, estimativa_cm2=estimate,
            erro_cm2=estimate - value, erro_percentual=100 * (estimate - value) / value, qualidade=arm['qualidade']))
    errors = np.array([p['erro_cm2'] for p in pairs])
    return dict(n=len(pairs), pares=pairs, referencias_sem_resultado=excluded,
        mae_cm2=float(np.abs(errors).mean()) if len(errors) else None,
        vies_cm2=float(errors.mean()) if len(errors) else None,
        rmse_cm2=float(np.sqrt(np.mean(errors ** 2))) if len(errors) else None,
        mape_percentual=float(np.mean([abs(p['erro_percentual']) for p in pairs])) if pairs else None,
        observacao='Inclui estimativas bloqueadas, identificadas em qualidade; não demonstra validação clínica. Referências precisam delimitar o mesmo segmento e medir área projetada.')


def main() -> None:
    """Executa auditoria reproduzível de fotos e salva imagens anotadas e contagens."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--imagens', type=Path, default=Path('Imagens'))
    parser.add_argument('--saida', type=Path, default=Path('validacao_atual'))
    parser.add_argument('--referencias', type=Path)
    parser.add_argument('--pose', type=Path, help='Peso local de pose para comparação controlada')
    args = parser.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    service, records = Servico(), []
    for path in sorted(args.imagens.iterdir()):
        if path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.heic', '.heif'}:
            continue
        try:
            options = parametros()
            if args.pose:
                options.pose = str(args.pose.resolve())
            report, images = service.analisar(path, options)
            import cv2
            for i, img in enumerate(images):
                cv2.imencode('.jpg', img)[1].tofile(str(args.saida / f'{path.stem}_S{i + 1}.jpg'))
        except Exception as exc:
            report = dict(imagem=path.name, status='rejeitada', flags=[str(exc)], bracos=[])
        records.append(report)
        print(path.name, report['status'], len(report['bracos']), flush=True)
    references = json.loads(args.referencias.read_text(encoding='utf-8')) if args.referencias else []
    summary = dict(imagens=len(records), com_segmento=sum(bool(r['bracos']) for r in records),
        segmentos=sum(len(r['bracos']) for r in records),
        qualidade=dict(Counter(a['qualidade'] for r in records for a in r['bracos'])),
        rejeicoes=dict(Counter(f for r in records if not r['bracos'] for f in r['flags'])),
        validacao_fisica=comparar(records, references), imagens_detalhes=records)
    (args.saida / 'auditoria.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    template = [dict(imagem=r['imagem'], segmento=i + 1, lado=a['lado'], area_cm2=None) for r in records for i, a in enumerate(r['bracos'])]
    (args.saida / 'referencias_preencher.json').write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Referências comparáveis:', summary['validacao_fisica']['n'])


if __name__ == '__main__':
    main()
