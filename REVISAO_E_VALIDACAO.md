# ProjetoFisioo — revisão e uso

## Diagnóstico por impacto

1. A contagem de pixels mede área projetada, não superfície curva nem volume/edema. Uma foto não identifica essas grandezas. Comparação direta com perimetria não valida área.
2. Escala fora do plano, inclinação e lente introduzem viés sistemático, elevado ao quadrado na área. Erro relativo pequeno de escala produz aproximadamente o dobro de erro relativo de área.
3. Roupa, tronco, fundo, braço contralateral e regiões ocultas contaminam a máscara. O original une todas as pessoas, sem associar instâncias.
4. Keypoints e extremos verticais do fallback não asseguram limites anatômicos. Braço cruzado/oculto não deve produzir medida aceita automaticamente.
5. Corredor estreito pode cortar pele; PCA de uma máscara ruim também produz eixo ruim. Nem PCA nem pele recuperam anatomia oculta.
6. Tag escolhida como maior região verde pode ser falso positivo. fitEllipse exige pelo menos cinco pontos, condição ausente no original; média dos eixos não corrige perspectiva.
7. Redimensionamento direto de masks.data pode ignorar padding do modelo; usar máscaras em resolução original. Baixa resolução perde bordas.
8. Polígonos inclusivos de fatias podem compartilhar pixels. O novo código atribui cada centro de pixel a uma única fatia; erro de discretização nas fronteiras continua existindo.
9. EXIF, alterações de postura e iluminação comprometem repetibilidade. Não havia controle de orientação nem exportação rastreável.
10. Não há evidência de exatidão clínica nem score calibrado de confiança.

## Implementação

O original PrototAntbYolo11.py foi preservado. fisio_pipeline.py é uma CLI independente, com funções testáveis, type hints e docstrings. Não carrega modelos na importação. Mantém HEIC e círculo de 19 mm.

| Melhoria | Impacto | Esforço |
|---|---|---|
| Definir área projetada e protocolo de referência | Muito alto | Médio |
| Rejeitar círculo ambíguo/inclinado; ArUco opcional | Alto | Médio |
| Associar pessoa e pose, intersectar pele, flag de corredor | Alto | Médio |
| PCA em coordenadas métricas; pixels exclusivos por fatia | Alto | Médio |
| Lote, falhas estruturadas, CSV/JSON e sobreposições | Alto | Baixo |
| Validar pele, limites e qualidade em amostra diversa | Muito alto | Alto |
| Treinar segmentação de antebraço ou avaliar SAM2 | Potencialmente alto | Alto |

### Instalação e exemplos (PowerShell, na pasta do projeto)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-fisio.txt
.\.venv\Scripts\python.exe fisio_pipeline.py Imagens --saida resultados_fisio
.\.venv\Scripts\python.exe fisio_pipeline.py Imagens --calibracao aruco --aruco-id 0 --aruco-mm 40 --saida resultados_aruco
.\.venv\Scripts\python.exe fisio_pipeline.py Imagens --pose yolo11x-pose.pt --device cpu
.\.venv\Scripts\python.exe -m unittest test_fisio_pipeline -v
```

Usar ambiente isolado: não misturar opencv-python e opencv-contrib-python manualmente; ambos fornecem cv2. O contrib inclui ArUco e não adiciona modelo neural. Ultralytics continua sendo a dependência pesada já prevista; SAM não foi adicionado. Os pesos padrão existem no projeto: pose nano reduz custo, mas segmentação x permanece cara. Pode-se fornecer um peso seg menor já baixado com --seg. Não há download automático de pesos.

Pasta é processada sem recursão. CSV tem uma linha por fatia ou uma linha vazia para imagem rejeitada; área total se repete por braço, portanto não somá-la entre linhas. JSON preserva parâmetros, homografia, confiança original dos keypoints e flags. Em ArUco, px_por_mm é null: uma homografia não possui escala escalar global. Coordenadas métricas e área de cada célula são calculadas no plano do marcador, sem rasterizar uma imagem retificada gigante. Área por fatia usa o centro do pixel; fronteiras têm erro de discretização.

Todas as medidas ficam em revisao_obrigatoria. Flags são regras heurísticas, não probabilidades nem atestado de qualidade. Falta de calibração não gera cm² fictícios. O círculo exige circularidade >=0,75, eixo menor >=20 px, razão de eixos >=0,90 e preenchimento da elipse entre 0,85 e 1,15. Esses limiares são iniciais, não validados. HSV pode ser configurado por --hsv-min e --hsv-max (H OpenCV: 0–179). Não aplicar adaptação automática sem conjunto de calibração rotulado.

ArUco usa DICT_4X4_50, ID 0 por padrão; --aruco-mm é a medida física da borda externa do quadrado preto, sem margem branca. Medir a impressão real. Colocar em suporte plano, com margem branca e no plano de referência. Uma homografia de quatro cantos não possui redundância para avaliar erro residual; o código não inventa confiança de reprojeção. Distância ao marcador, curvatura e distorção da lente continuam limitações. Círculo quase frontal permite escala aproximada, não homografia única confiável. Marcadores fixados sobre pele curva não definem plano comum do braço.

### Close-up com pontos manuais

Criar pontos.json, com coordenadas x/y em pixels após orientação EXIF:

```json
{
  "foto.jpg": [
    {"lado": "esquerdo", "cotovelo": [120, 180], "punho": [330, 610]}
  ]
}
```

```powershell
.\.venv\Scripts\python.exe fisio_pipeline.py foto.jpg --pontos pontos.json
```

Coordenadas do exemplo são ilustrativas; substituir pelas reais. Modo manual usa pele e corredor sem YOLO, identificado por flag. Não há fallback por extremos. Não permite aceitar anatomia oculta. Conferir máscaras e limites em cada sobreposição. A linha branca representa os pontos iniciais; eixo PCA numérico fica no JSON, as cores mostram a atribuição das fatias. Guardar os pontos manuais junto ao resultado.

## Protocolo de validação proposto (não executado)

1. Definir primeiro a finalidade: acompanhamento de área projetada em postura fixa ou volume? Para volume/superfície real, adotar referência 3D e outro método; perimetria mede circunferência e serve como desfecho complementar, não verdade de área projetada.
2. Geometria: pelo menos 10 silhuetas planas de área conhecida por dimensões físicas, incluindo formas de antebraço. Fotografar em 3 distâncias × 3 ângulos (0°, 15°, 30°) × 2 iluminações = 180 fotos. Repetir pelo menos 30 aquisições com reposicionamento completo. Incluir uma régua/grade independente que não seja usada na calibração.
3. Estudo piloto humano: 20 participantes, diversidade de tons de pele, dimensões e pelos; 2 braços × 3 condições de luz × 2 distâncias × 2 ângulos = 480 fotos. Acrescentar duas repetições reposicionadas da condição padrão para os 40 braços (80 fotos). Números são desenho inicial, não cálculo de poder nem garantia de representatividade. Resolver consentimento e finalidade com a equipe responsável antes de coleta.
4. Dois avaliadores delimitam punho/cotovelo e contorno visível independentemente, resolvem divergências e quantificam concordância. Referência de máscara manual testa segmentação, mas não valida a escala física por si só. Evitar ajustar HSV no conjunto de teste; separar participantes entre desenvolvimento e teste.
5. Medir MAE em cm² = média de |estimativa−referência|, erro percentual absoluto = 100×|erro|/referência para referências positivas, viés médio, RMSE, percentis e limites de concordância de Bland–Altman. Para fatias, garantir mesmos limites anatômicos. Reportar também Dice/IoU, erro dos limites em mm, repetibilidade intra/interavaliador e taxa de rejeição com motivos.
6. Apresentar resultados por tom de pele, luz, ângulo, distância, formato de arquivo, lado e método de calibração. Intervalos de confiança devem respeitar agrupamento por participante. Reportar casos rejeitados, sem excluí-los silenciosamente das conclusões. Estabelecer tolerância clínica antes do teste com o fisioterapeuta; nenhum limiar clínico foi inventado aqui.
7. Testes de falha: roupa, fundo semelhante à pele, duas pessoas, tags duplicadas, tag inclinada, braço cruzado, corte no enquadramento, reflexos e borramento. Avaliar se a rejeição funciona, além do erro nas imagens aceitas.

## Checklist de aquisição

- Câmera fixa em suporte, lente principal, sem ultrawide, filtros de beleza ou zoom digital. Iniciar em 70–100 cm e ajustar para enquadrar todo o segmento; fixar distância após ensaio de resolução. Não é uma distância clinicamente validada.
- Sensor aproximadamente paralelo ao plano de referência, eixo óptico perpendicular, braço no centro da imagem. Registrar distância e evitar perspectiva oblíqua.
- Antebraço apoiado, postura e rotação reproduzíveis; cotovelo e punho visíveis e marcados por avaliador. Mesmo lado e postura em sessões sucessivas. Sem roupas, acessórios ou outro membro sobre o segmento.
- Círculo de 19 mm medido, fosco, totalmente visível; ou ArUco plano de cerca de 40 mm, medida real verificada. Ao lado do segmento e próximo da mesma profundidade, sem cobrir pele medida. Não assumir que tag colada sobre curvatura seja coplanar.
- Fundo fosco uniforme contrastante com pele e verde; luz difusa bilateral, sem sombras duras/reflexos. Fixar exposição e balanço de branco quando possível.
- Garantir tag com pelo menos 20 px no menor eixo (alvo de aquisição >=40 px, sujeito a validação), foco nítido e imagem original sem recompressão de mensageiro.
- Registrar data, postura, distância, câmera, iluminação e responsável; revisar contorno e fatias antes de comparar sessões. Não interpretar mudança de área isoladamente como edema ou volume.

## Próximas etapas

Calibrar intrínsecos e distorção da câmera; aplicar undistort antes de todas as coordenadas e deteções. Avaliar placa com múltiplos marcadores para redundância. Criar anotações próprias de pele/antebraço; comparar segmentação treinada, GrabCut e SAM2 pelo erro de área e custo computacional. Para braços curvos ou flexionados, estudar linha central com normais locais em vez de PCA reta, após validar limites anatômicos. Registrar versões e hashes de pesos para rastreabilidade de experimentos.

Referências técnicas: https://docs.opencv.org/4.5.3/d9/d6a/group__aruco.html ; https://github.com/opencv/opencv/blob/4.x/doc/tutorials/features2d/homography/homography.markdown ; https://docs.ultralytics.com/reference/engine/results/ ; https://docs.ultralytics.com/tasks/segment/
