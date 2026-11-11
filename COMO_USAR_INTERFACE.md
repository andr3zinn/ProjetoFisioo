# Interface anterior (Tkinter)

**O atalho Abrir Fisio.cmd agora abre a interface web moderna. Consulte [COMO_USAR_WEB.md](COMO_USAR_WEB.md) para o fluxo atual.** As instruções abaixo se referem à janela antiga, preservada em fisio_interface.py.

Abra **Abrir Fisio.cmd** com dois cliques ou execute a tarefa **Fisio: abrir interface** no VS Code. Usa o ambiente `.venv` já instalado. Não requer Streamlit, navegador ou novas bibliotecas pesadas; Tkinter acompanha o Python disponível nesta máquina.

1. Clique em **Abrir foto** e selecione JPG, PNG ou HEIC.
2. Confira o marcador: círculo verde, diâmetro real padrão 19 mm; ou ArUco DICT_4X4_50 com ID e lado externo do quadrado preto medidos.
3. Clique em **Analisar automaticamente**. Aguarde o carregamento dos modelos em CPU. A janela continua responsiva e mostra progresso sem inventar porcentagem.
4. Confira o segmento colorido. Se houver vários braços, escolha o segmento na lista. A tabela mostra área por fatia; o valor grande é a soma das fatias daquele braço.
5. Se os limites estiverem errados ou for close-up, selecione o lado e clique em **Marcar cotovelo e punho**. Clique primeiro no cotovelo e depois no punho. A análise inicia após o segundo clique. Clique no botão novamente para reiniciar a marcação.
6. Use **Alternar original / resultado** para comparar. Se a foto não mostrar limites anatômicos, recapture; não invente pontos.
7. Clique em **Exportar resultados** e escolha uma pasta. Cada exportação cria uma subpasta exclusiva com JSON, CSV e sobreposições PNG. Mesmo uma tentativa rejeitada pode ser exportada para registrar o motivo.

Os arquivos não são enviados a um servidor pela aplicação. Escolha uma pasta local se não quiser sincronização pelo OneDrive. A aplicação não cria histórico automático de pacientes e mantém apenas a foto atual na sessão.

As imagens grandes são reduzidas para no máximo 1600 pixels no maior lado para processamento e exportação. A tag é calibrada na imagem original; sua transformação é ajustada às coordenadas reduzidas. Isso preserva a geometria da escala, mas bordas e máscaras sofrem discretização. O JSON registra ambas as resoluções, os parâmetros e os pontos manuais nas coordenadas processadas.

Alterar a configuração não altera uma medida já calculada: clique em analisar novamente. A exportação usa os parâmetros da análise realizada.

A marcação manual usa pele e corredor sem a máscara YOLO de pessoa; pode incluir fundo parecido com pele. Revise o contorno, não apenas os dois pontos. A pele coberta por tag, relógio ou roupas não é recuperada. A escala do círculo não corrige perspectiva, e ArUco corrige apenas o plano do marcador. Resultados são estimativas de área projetada 2D e exigem revisão; não são volume nem superfície curva.

Para abrir pelo terminal integrado, se precisar verificar uma mensagem de erro:

```powershell
.\.venv\Scripts\python.exe fisio_interface.py
```

Próximas melhorias possíveis: edição do contorno, comparação entre sessões com identificadores locais, geração de relatório para impressão e empacotamento em instalador. Antes de comparar evolução, validar repetibilidade e limites anatômicos com o protocolo do projeto.
