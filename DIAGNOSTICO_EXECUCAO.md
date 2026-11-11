# Correções de execução e unidades — 10/11/2026

## Problema reproduzido

O serviço da porta 8765 respondeu a /api/config sem identificação de versão. Era uma implementação anterior. O atalho antigo abria a porta ocupada sem conferir a versão do Python em memória. Alterar os arquivos ou manter o VS Code aberto não recarrega um processo Python já iniciado.

## Correções

- Inicialização identifica o aplicativo e a versão de todos os arquivos relevantes. A interface só habilita análise quando o serviço está atualizado.
- Porta ocupada por instância antiga não é reutilizada cegamente: uma porta livre é escolhida, sem encerrar outros processos. Nesta execução a instância atual ficou em http://127.0.0.1:8766/.
- A porta é reservada exclusivamente no Windows. Adicionado teste de regressão para conflito de porta e limpeza de inicialização incompleta.
- O atalho mostra o processo de inicialização e seus erros. O VS Code não é obrigatório; o processo Python deve permanecer ativo.
- A biblioteca da pasta Imagens pode ser acessada pela própria página, sem upload repetido. As fotos originais são preservadas.
- Requisições e prévias receberam tempos máximos para não deixar a página indefinidamente em carregamento.
- Campos separados para área em cm² e comprimento em cm. Tabela inclui largura média projetada, calculada como área/comprimento de seção. Não existe cálculo de circunferência no aplicativo.

## Verificação

- Dezoito testes de regressão passaram.
- Testes de todas as 26 fotos repetidos via HTTP e preservados em teste_todas_imagens/http/resultados.json. Um processamento concluído pode conter rejeição de tag/pose: isso não equivale a área válida.
- Na tela foram reproduzidos carregamento local e análise de Img1.jpeg, além do carregamento/análise de IMG_8763.HEIC.
- A tela da HEIC apresentava 58,86 cm² na seção 0–5 cm. O comprimento total exibido era 32,96 cm. A primeira cifra é área, não circunferência nem comprimento. A distinção de unidades não comprova acerto anatômico ou de escala.

## Como abrir a versão correta

Execute Abrir Fisio.cmd e use a aba que ele abrir. Mantenha a janela do serviço aberta enquanto utiliza. Confirme “Serviço atualizado · conectado” no topo. Escolha Img1.jpeg na lista da pasta Imagens e clique em Estimar medidas. Se uma foto não contiver escala conhecida ou limites anatômicos visíveis, não force uma conversão física.

As referências visuais da internet estão em REFERENCIAS_FOTOGRAFIA.md; elas orientam postura e enquadramento, sem servir como calibração ou validação clínica.
