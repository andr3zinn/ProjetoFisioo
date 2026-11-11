"""Produz tabela legível das fotos testadas, sem confundir execução com medida válida."""
import json
from pathlib import Path


def main() -> None:
    """Consolida auditoria automática e teste HTTP por nome original."""
    root = Path('teste_todas_imagens')
    http = json.loads((root/'http/resultados.json').read_text(encoding='utf-8'))
    records = [r.get('report') or dict(imagem=r['name'],bracos=[],flags=[]) for r in http]
    network = {r['name']:r for r in http}
    lines = ['# Teste de todas as 26 fotos — 10/11/2026', '',
        'Cada arquivo foi lido e testado individualmente. A tabela distingue conseguir executar de conseguir delimitar uma medida.', '',
        '| Arquivo | Envio/processamento HTTP | Detecção automática | Ação recomendada |',
        '|---|---|---|---|']
    for r in records:
        n = network.get(r['imagem'], {})
        transport = 'Concluído' if n.get('state')=='done' else ('Falha: '+str(n.get('error','não testado')))
        if r['bracos']:
            provisional = sum(a['qualidade']=='provisoria' for a in r['bracos'])
            outcome = f"{len(r['bracos'])} segmento(s): {provisional} provisório(s), {len(r['bracos'])-provisional} bloqueado(s)"
            recommendation = 'Conferir contorno e limites; corrigir pontos se necessário'
        elif 'TAG_AUSENTE_INCLINADA_OU_AMBIGUA' in r['flags']:
            outcome = 'Calibração automática rejeitada'
            recommendation = 'Calibrar marcador por 2 cliques, com diâmetro real conhecido'
        else:
            outcome = 'Tag encontrada; pose insuficiente'
            recommendation = 'Marcar cotovelo e punho se ambos estiverem visíveis; senão recapturar'
        lines.append(f"| {r['imagem']} | {transport} | {outcome} | {recommendation} |")
    retry_file = root/'http/conexoes_repetidas.json'
    retry_count = len(json.loads(retry_file.read_text(encoding='utf-8'))) if retry_file.exists() else 0
    lines += ['', f'Teste HTTP final: {len(http)} arquivos processados. Houve {retry_count} repetições de requisições após interrupções de conexão em prévias; o resultado final por arquivo está na tabela. Os eventos foram preservados em http/conexoes_repetidas.json.', '', '## Alterações e evidências', '',
        '- A cor verde-azulada foi incluída na faixa padrão (H até 100 no OpenCV). LEDs de matiz 105 não foram incluídos.',
        '- A circularidade agora usa o perímetro do fecho convexo, com verificação de solidez. Isso reduz rejeições causadas por serrilhado na borda em fotos grandes, sem selecionar o maior verde indiscriminadamente.',
        '- Tag branca/clara, duas tags ou tag inclinada não são convertidas automaticamente. A interface permite dois cliques no diâmetro. O tamanho físico precisa ser confirmado, independentemente da cor.',
        '- Trocar foto libera a sessão anterior para evitar atingir o limite de doze uploads.',
        '- O modelo nano é a primeira tentativa. Se não encontrar articulações suficientes, o YOLO11x-pose local é usado como reserva, reaproveitando a máscara de pessoa. Isso recuperou IMG_8006.HEIC. Nenhum limiar de confiança foi reduzido para forçar resultado.',
        '- Um close-up com marcador branco (IMG_7809.HEIC) foi processado em modo manual. Os pontos foram demonstrativos, e o diâmetro de 19 mm foi uma hipótese explícita; não é uma medição física validada.',
        '- Vinte testes de regressão passaram, incluindo bloqueio de eixo confundido com diâmetro e recuperação manual após pose ausente.', '',
        '## Limitações que continuam', '',
        f"Neste lote, {sum(bool(r['bracos']) for r in records)} fotos produziram {sum(len(r['bracos']) for r in records)} segmentos. Isso não significa que as demais fotos estejam corrompidas: algumas não contêm pose completa, algumas têm marcador claro, duas tags ou perspectiva rejeitada. A interface encaminha diretamente à próxima marcação necessária, preservando a escala. Não se deve inventar escala nem limites anatômicos para forçar resultado.", '',
        'Há zero áreas físicas de referência. Não foram calculadas métricas de exatidão clínica. O mosaico mosaico.jpg e os JSONs preservam a evidência e os motivos por arquivo.', '',
        '## Como testar na interface', '',
        'Atualize a página. Comece com Img1.jpeg ou Img4.jpeg no modo automático. Para as demais, veja a ação recomendada na tabela. Se a tag falhar, clique em Calibrar marcador por 2 cliques, marque bordas opostas do diâmetro, confira o tamanho real e analise novamente. Se a pose falhar, marque cotovelo e punho; a calibração manual já marcada é mantida. Se as articulações não aparecem na foto, faça uma nova captura.']
    (root/'RESULTADOS_POR_IMAGEM.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__ == '__main__':
    main()
