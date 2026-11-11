# ProjetoFisioo

Aplicação local para estimativa experimental da **área projetada 2D do antebraço** em fotos JPG, PNG e HEIC. A interface usa HTML, CSS e JavaScript; o processamento usa Python, OpenCV, NumPy, Pillow/pillow-heif e Ultralytics YOLO.

O projeto **não mede circunferência, volume nem superfície curva 3D**. As áreas dependem da dimensão física do marcador, da perspectiva, da máscara e dos limites anatômicos. Os resultados exigem revisão e ainda não possuem validação clínica com referência independente.

## Instalação no Windows

Requer Python 3.12 (versão utilizada nos testes) e Git para clonar o repositório.

Na pasta do projeto, pelo PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-fisio.txt
.\.venv\Scripts\python.exe preparar_modelos.py
.\.venv\Scripts\python.exe fisio_web.py
```

O comando de preparação baixa os três pesos oficiais por meio do Ultralytics. Os arquivos são grandes e requerem internet nessa etapa. As fotos são processadas localmente; o aplicativo não envia imagens a um serviço de análise externo.

Depois da instalação, também é possível abrir **Abrir Fisio.cmd** com dois cliques ou executar a tarefa **Fisio: abrir interface** no VS Code. Use a aba que o programa abrir: uma porta ocupada por versão antiga faz o serviço escolher outra porta local. O topo deve indicar **Serviço atualizado · conectado**. Mantenha o processo Python ativo durante o uso; o VS Code não é obrigatório.

## Uso

1. Coloque suas próprias fotos em `Imagens/` e escolha uma delas pela lista da interface, ou selecione/arraste um arquivo (até 30 MB).
2. Confirme a referência física. O círculo verde usa **19 mm de diâmetro como valor informado padrão**; altere se a dimensão real for outra. ArUco usa DICT_4X4_50, ID e lado do quadrado preto informados.
3. Clique em **Estimar medidas**. O modelo nano é a primeira tentativa; o YOLO11x-pose local é usado como reserva se não houver articulações suficientes. As máscaras de pessoa são refinadas por cor de pele.
4. Se a tag não for encontrada, o fluxo abre a marcação ampliada do adesivo. Marque somente duas bordas opostas do diâmetro, **não cotovelo e punho**. Para um marcador não detectado, primeiro clique no centro para ampliar.
5. Se a pose não for suficiente, a interface encaminha à marcação de **cotovelo e punho**, mantendo a calibração. Confirme os dois pontos para medir.
6. Revise os contornos, as seções e as unidades. Área aparece em cm²; comprimento aparece em cm. Uma marcação incompatível com a tag detectada é bloqueada.
7. Baixe o ZIP com JSON, CSV e imagens anotadas. O status provisório ou bloqueado e os parâmetros ficam registrados.

Uma foto sem marcador de dimensão conhecida ou sem limites anatômicos visíveis pode exigir nova captura. Não são inventadas medidas para preencher esses casos.

## Testes

Os testes de geometria, serviço e HTTP usam imagens sintéticas temporárias e podem ser executados **sem fotos de pacientes e sem os pesos dos modelos**:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

A suíte contém 20 testes. Ela verifica execução e regressões, não exatidão clínica. Para repetir o lote com suas próprias fotos:

```powershell
.\.venv\Scripts\python.exe testar_pasta_web.py
.\.venv\Scripts\python.exe validar_fisio.py --imagens Imagens --saida validacao_atual
```

`validar_fisio.py` gera uma planilha JSON de referências a preencher e calcula MAE, viés, RMSE e MAPE somente quando áreas de referência independentes são fornecidas. Circunferência medida com fita não é referência direta de área projetada.

## Organização

| Arquivo | Responsabilidade |
|---|---|
| `fisio_web.py` | Servidor HTTP local, sessões temporárias, versão ativa e exportação |
| `web/` | Interface, marcações guiadas e apresentação dos resultados |
| `fisio_servico.py` | Calibração, transformação de resolução e coordenação da análise |
| `fisio_pipeline.py` | Leitura HEIC, tag, YOLO, máscara, eixo PCA e integração das fatias |
| `fisio_visual.py` | Contornos, limites das seções e legendas |
| `preparar_modelos.py` | Preparação explícita dos pesos locais |
| `verificar_execucao.py` | Diagnóstico da versão e do Python em execução |
| `test_*.py` | Testes sem dados privados |
| `Protot*.py`, `proj*.py` | Protótipos históricos; não são a interface principal |

## Dados e limitações

Fotos, pesos, ambientes Python, capturas de tela e relatórios de pessoas foram excluídos do Git. As imagens da pasta `Imagens` devem ser adicionadas localmente por quem usar o projeto. Algumas ferramentas de reprodução fazem referência a nomes de fotos do desenvolvimento e exigem esses arquivos locais.

Fotos grandes são reduzidas para até 1600 px no maior lado; a calibração é calculada no original e transformada para essa resolução. A segmentação por cor pode perder pele e incluir fundos semelhantes. A tag e acessórios cobrem pele que o algoritmo não recupera. Uma homografia de ArUco corrige somente um plano. A pose pode errar mesmo com confiança alta: sempre revise os limites.

As heurísticas de bloqueio são controles de engenharia, não limites clínicos validados. Não houve retreinamento do YOLO específico para antebraços. Os modelos e dependências mantêm suas próprias licenças e atribuições; consulte a [documentação do Ultralytics](https://docs.ultralytics.com/).

Mais detalhes: [uso da interface](COMO_USAR_WEB.md), [protocolo de validação](REVISAO_E_VALIDACAO.md) e [referências de fotografia](REFERENCIAS_FOTOGRAFIA.md).
