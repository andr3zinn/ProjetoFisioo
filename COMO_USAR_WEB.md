# Fisio — interface moderna no navegador

Abra **Abrir Fisio.cmd** com dois cliques. O atalho inicia o serviço Python local e abre o navegador em **http://127.0.0.1:8765**. Também é possível usar a tarefa **Fisio: abrir interface** no VS Code.

**Atualização de inicialização:** não é necessário manter o VS Code aberto. É necessário manter o serviço Python em execução. O atalho agora abre uma janela de inicialização; mantenha-a aberta enquanto usa o aplicativo. Se a porta estiver ocupada por versão antiga, o atalho escolhe outra (por exemplo 8766). Use a aba que ele abrir, não um endereço antigo salvo. O topo deve informar **Serviço atualizado · conectado**. Versões antigas são bloqueadas pela interface atual, e nenhuma instância antiga é encerrada à força.

Você pode escolher diretamente uma das 26 fotos pela lista **Ou abra diretamente uma foto da pasta Imagens**, sem passar pelo seletor de uploads. As fotos originais são preservadas. O comando verificar_execucao.py ajuda a conferir versão, Python e pasta do serviço em execução.

## Fluxo de uso

1. Selecione uma foto ou arraste JPG, PNG ou HEIC para a área de envio (até 30 MB).
2. Confira o marcador e sua dimensão física: círculo verde de 19 mm por padrão, ou ArUco DICT_4X4_50 com lado do quadrado preto e ID reais.
3. Clique em **Estimar medidas**. Aguarde a análise local em CPU; o carregamento inicial dos modelos pode levar mais tempo.
4. Veja as fatias sobre a foto e a tabela abaixo. Se houver vários braços, escolha o segmento na lista. A área total soma apenas as fatias daquele segmento.
5. Para corrigir limites, use **2. Marcar cotovelo e punho**. Clique no cotovelo e depois no punho, escolha o lado e confirme em **Medir com os dois pontos**. Use o mesmo botão de marcação para refazer pontos. Esses cliques são diferentes da marcação do diâmetro do adesivo.
6. Alterne entre **Original** e **Fatias** e confira toda a máscara, não apenas os pontos.
7. Clique em **Baixar relatório** para receber um ZIP com CSV, JSON e imagens PNG. Tentativas rejeitadas também podem ser exportadas com seus motivos.

### Se a foto não for reconhecida

O programa tenta um modelo de pose de reserva se o primeiro falhar. Se ainda faltarem articulações, a própria tela abre a etapa de marcar cotovelo e punho e preserva a calibração.

Para conferir a tag, use **1. Conferir o diâmetro da tag**. A marcação acontece em uma janela ampliada do adesivo. Se o marcador não foi detectado, primeiro clique no centro dele para ampliar e depois marque duas bordas opostas. **Não marque cotovelo e punho nessa janela.** Linhas incompatíveis com a tag detectada são bloqueadas. Você também pode escolher **Usar marcador detectado e medir**.

Após confirmar o diâmetro, a análise continua e, se necessário, encaminha à marcação do braço. Isso funciona também com marcador claro de dimensão conhecida. Não use automaticamente 19 mm se a tag real tiver outra medida. Cotovelo e punho devem estar visíveis; não invente articulações fora do enquadramento.

O teste de cada uma das 26 fotos está em teste_todas_imagens/RESULTADOS_POR_IMAGEM.md. Trocar de foto agora libera o upload temporário anterior. Calibração automática cobre verde e verde-azulado; tags ambíguas ou inclinadas continuam exigindo revisão.

Modificar parâmetros não modifica o relatório anterior. Analise novamente para aplicar mudanças. Não há medidas fictícias ou histórico simulado na página.

## Execução e testes

Nenhuma nova biblioteca Python ou ferramenta de frontend é necessária. A interface usa HTML/CSS/JS locais, servidor HTTP da biblioteca padrão e o mesmo serviço de medição. Sem CDN ou fontes externas.

```powershell
.\.venv\Scripts\python.exe fisio_web.py
.\.venv\Scripts\python.exe -m unittest test_fisio_pipeline test_fisio_servico test_fisio_web -v
```

Para encerrar o serviço iniciado pelo terminal, use Ctrl+C nesse terminal. Fechar a aba não encerra o serviço iniciado pelo atalho. Reabrir o atalho reutiliza a porta padrão. Para outra porta: `fisio_web.py --porta 8766`. A versão Tkinter anterior foi preservada em fisio_interface.py, mas o atalho e as tarefas agora usam a interface web.

## Fotos, processamento e limites

O servidor atende somente em 127.0.0.1. As fotos são enviadas pelo navegador ao Python neste computador, sem hospedagem externa. Arquivos ficam temporariamente na pasta temporária do Windows; são removidos no encerramento normal do servidor. Não existe histórico permanente de pacientes. Até 12 fotos são mantidas por instância; reinicie o serviço para limpar a sessão. Downloads ficam na pasta configurada pelo navegador, que pode ser sincronizada pelo OneDrive.

O processamento é limitado a 1600 px no maior lado. A calibração usa a imagem original e a transformação é ajustada à resolução reduzida. O JSON registra ambas as resoluções, os parâmetros e os pontos marcados em coordenadas processadas. Bordas continuam sujeitas a discretização.

O modo manual usa pele e corredor sem máscara YOLO de pessoa; fundos parecidos com pele podem ser incluídos. Pele coberta por tag, relógio ou roupa não é recuperada. Círculo não corrige perspectiva; ArUco corrige somente o plano do marcador. A estimativa é de área projetada 2D, sem volume nem superfície curva; exige revisão visual e validação pelo protocolo do projeto.

## Verificações realizadas

- Dez testes automáticos: geometria, redução de resolução, exportação, upload/análise/download HTTP e rejeição de chamadas sem sessão válida ou com origem externa.
- Envio de Img1.jpeg pelo navegador, inferência real, preenchimento de tabela e visualização das fatias.
- Ajuste manual por clique e conferência responsiva pelo navegador.

Isso confirma funcionamento do fluxo; não demonstra precisão clínica.
