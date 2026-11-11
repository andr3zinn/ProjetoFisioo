# Como testar no VS Code

O ambiente Python do projeto está em `.venv`. As configurações locais usam esse ambiente diretamente, sem precisar ativá-lo no terminal.

1. Abra esta pasta no VS Code.
2. Pressione **Ctrl+Shift+P**, escolha **Tasks: Run Task / Tarefas: Executar Tarefa**.
3. Selecione **Fisio: testar funcionamento**. O terminal deve terminar com `Ran 20 tests` e `OK`. São testes de geometria, serviço, interface HTTP e exportação, não de precisão clínica.
4. Execute a tarefa **Fisio: processar todas as fotos** e aguarde o terminal terminar. O modelo de segmentação é grande e a primeira execução em CPU pode demorar.
5. Abra `resultados_teste/resultados.json` ou `resultados.csv`. Cada imagem tem um status e flags; ausência de medida é registrada como rejeição. `revisao_obrigatoria` significa que houve medida, que ainda precisa ser conferida.
6. Abra as imagens PNG geradas na mesma pasta. Confira se as regiões coloridas cobrem apenas o segmento desejado, sem roupa, fundo, mão ou outro braço. Compare limites anatômicos e procure cortes artificiais nas laterais.

Com a extensão Python Debugger instalada, também é possível pressionar **F5** e escolher **Fisio: processar fotos (CPU)**. As tarefas acima não dependem dessa extensão.

Alternativa no terminal PowerShell integrado (na raiz do projeto):

```powershell
.\.venv\Scripts\python.exe -m unittest test_fisio_pipeline test_fisio_servico test_fisio_web test_validacao -v
.\.venv\Scripts\python.exe -u fisio_pipeline.py Imagens --saida resultados_teste --device cpu
```

Para testar apenas uma foto:

```powershell
.\.venv\Scripts\python.exe -u fisio_pipeline.py Imagens\Img1.jpeg --saida resultado_uma_foto --device cpu
```

Não reduza os filtros apenas para obter uma medida. Tag rejeitada, pose ausente e máscara inadequada são falhas que precisam de revisão da captura ou de anotação manual. A área é projetada em 2D; os testes não validam superfície 3D, volume ou edema. O protocolo completo está em `REVISAO_E_VALIDACAO.md`.
