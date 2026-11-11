'use strict';
const $ = id => document.getElementById(id);
const state = {token: '', ready: false, id: null, name: '', image: null, overlay: null, report: null, reference: null, arm: 0, points: [], tagPoints: [], tagDraft: [], tagCrop: null, tagPhase: '', tagging: false, marking: false, busy: false, view: 'original', revision: 0, recovery: null};
const labels = {
  POSE_MODELO_RESERVA_UTILIZADO: 'O primeiro modelo não encontrou articulações suficientes. A pose foi recuperada pelo YOLO11x local; confira os limites sugeridos.',
  CALIBRACAO_MANUAL_DIAMETRO: 'Escala definida manualmente pelos extremos do diâmetro. Confira os dois pontos e a dimensão física; a inclinação não foi corrigida.',
  COBERTURA_LONGITUDINAL_INSUFICIENTE: 'A máscara não cobre suficientemente o eixo entre cotovelo e punho. A medida foi bloqueada.',
  PERSPECTIVA_NAO_CORRIGIDA: 'A escala do círculo não corrige perspectiva. Confira o ângulo da captura.',
  PLANO_COPLANAR_NAO_VERIFICADO: 'Confirme que o marcador está próximo da mesma profundidade do segmento.',
  DISTORCAO_LENTE_NAO_CORRIGIDA: 'A distorção da lente não foi corrigida. Evite lentes ultrawide e as bordas da foto.',
  TAG_AUSENTE_INCLINADA_OU_AMBIGUA: 'Não foi possível validar uma única tag verde. Confira cor, foco, inclinação e visibilidade.',
  ARUCO_AUSENTE_OU_AMBIGUO: 'Não foi encontrado um único ArUco com o ID selecionado.',
  ARUCO_RESOLUCAO_BAIXA: 'O ArUco está pequeno demais na imagem. Faça uma captura mais nítida ou próxima.',
  NENHUM_BRACO_MENSURAVEL: 'Não foi possível delimitar um braço. Se cotovelo e punho estiverem visíveis, tente a marcação manual.',
  PELE_HEURISTICA: 'A segmentação por cor pode perder pele, pelos e sombras. Pele coberta pelo marcador não é recuperada.',
  REVISAO_VISUAL_OBRIGATORIA: 'Confira se as cores cobrem apenas o segmento desejado e se os limites anatômicos estão corretos.',
  EIXO_RETO_APROXIMADO: 'O eixo foi aproximado por uma reta. Braços curvos ou flexionados exigem atenção.',
  EIXO_PCA_INCERTO: 'O eixo ajustado pela máscara está incerto. Revise pontos e contorno.',
  MASCARA_FRAGMENTADA: 'A máscara ficou fragmentada e pode ter excluído parte do segmento.',
  MASCARA_LIMITADA_PELO_CORREDOR: 'O limite lateral pode ter cortado o braço. Não aceite a área sem revisar a máscara.',
  MASCARA_NA_BORDA: 'A máscara toca a borda da foto. Parte do segmento pode estar fora do enquadramento.',
  PONTOS_MANUAIS_SEM_MASCARA_PESSOA: 'Modo manual: pele e corredor sem máscara de pessoa. Confira se o fundo foi incluído.',
  IMAGEM_REDUZIDA_PARA_PROCESSAMENTO: 'A foto foi reduzida para processamento local; a conversão de escala foi preservada.',
  POSE_OU_PESSOA_AUSENTE: 'Os modelos não identificaram pessoa ou pose suficiente para delimitar o segmento.',
  KEYPOINTS_BAIXA_CONFIANCA_ESQUERDO: 'Pontos automáticos do braço esquerdo com confiança insuficiente.',
  KEYPOINTS_BAIXA_CONFIANCA_DIREITO: 'Pontos automáticos do braço direito com confiança insuficiente.',
};
const number = (n, digits = 2) => new Intl.NumberFormat('pt-BR', {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(n);
function notice(text, error = false) { $('status').textContent = text; $('status').hidden = !text; $('status').classList.toggle('error', error); }
function busy(value, title = 'Analisando sua foto', description = 'Os modelos em CPU podem levar mais tempo na primeira análise.') {
  state.busy = value;
  document.body.classList.toggle('working', value);
  $('busyOverlay').hidden = !value;
  $('busyTitle').textContent = title; $('busyText').textContent = description;
  for (const id of ['choose', 'replace', 'analyze', 'manual', 'markTag']) $(id).disabled = value || !state.ready || (id !== 'choose' && !state.id);
  $('librarySelect').disabled = value || !state.ready;
  $('analyze').disabled = value || !state.ready || !state.id || (state.marking && state.points.length !== 2);
  $('analyze').firstChild.textContent = state.points.length === 2 ? 'Medir com os pontos marcados ' : 'Estimar medidas ';
}
function resetReport() {
  state.revision++;
  state.report = null; state.overlay = null; state.arm = 0; state.view = 'original';
  $('results').hidden = true; $('overlay').disabled = true; $('zoom').disabled = true;
  $('step3').classList.remove('current');
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path === '/api/upload' || path === '/api/library' ? 120000 : 30000);
  try {
    const response = await fetch(path, { ...options, signal:controller.signal, headers: {'X-Fisio-Token': state.token, ...options.headers}});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Não foi possível concluir. Tente novamente.');
    return data;
  } catch(error) {
    if (error.name === 'AbortError') throw Error('O serviço local não respondeu a tempo. Execute Abrir Fisio.cmd e use a aba atualizada.');
    throw error;
  } finally { clearTimeout(timer); }
}
async function loadImage(url) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await new Promise((resolve, reject) => { const image = new Image(); const timer=setTimeout(() => { image.onload=null; image.onerror=null; reject(Error('A prévia não respondeu. Tente selecionar a foto novamente.')); },15000); image.onload = () => {clearTimeout(timer);resolve(image);}; image.onerror = () => {clearTimeout(timer);reject(Error('Não foi possível carregar a prévia. Tente selecionar a foto novamente.'));}; image.src = url + (attempt ? `${url.includes('?') ? '&' : '?'}retry=${Date.now()}` : ''); });
    } catch (error) { if (attempt) throw error; }
  }
}
function draw() {
  const image = state.view === 'overlay' && state.overlay ? state.overlay : state.image;
  if (!image) return;
  const canvas = $('canvas'); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
  if (state.view === 'original' && state.reference) {
    const r=state.reference;
    context.beginPath(); context.ellipse(r.center[0],r.center[1],r.axes[0]/2,r.axes[1]/2,r.angle*Math.PI/180,0,Math.PI*2);
    context.strokeStyle='#ffcc36';context.lineWidth=4;context.stroke();
  }
  if (state.marking || state.tagging) {
    const radius = Math.max(7, canvas.width / 100);
    (state.tagging ? state.tagPoints : state.points).forEach(([x, y], i) => {
      context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fillStyle = '#377eae'; context.fill(); context.strokeStyle = '#fff'; context.lineWidth = Math.max(2, radius / 4); context.stroke();
      context.font = `600 ${Math.max(15, canvas.width / 50)}px Segoe UI`; context.lineWidth = 4; context.strokeStyle = '#fff';
      const label = state.tagging ? `Tag ${i + 1}` : (i ? 'Punho' : 'Cotovelo'); const tx = Math.min(x + radius * 1.4, canvas.width - radius * 9); const ty = Math.max(radius * 3, y - radius * 1.4);
      context.strokeText(label, tx, ty); context.fillStyle = '#173b35'; context.fillText(label, tx, ty);
    });
  }
  $('original').classList.toggle('selected', state.view === 'original'); $('overlay').classList.toggle('selected', state.view === 'overlay');
}
async function upload(file, libraryName = '') {
  if ((!file && !libraryName) || state.busy || !state.ready) return;
  if (file && file.size > 30 * 1024 * 1024) { notice('A imagem precisa ter até 30 MB.', true); return; }
  busy(true, 'Preparando sua foto', 'Liberando a foto anterior e organizando a nova captura.');
  if (state.id) await api('/api/release', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:state.id})}).catch(() => {});
  resetReport(); state.points = []; state.tagPoints = []; state.tagging = false; state.marking = false; state.id = null;
  state.reference=null; state.recovery=null; $('recovery').hidden=true; $('markingPrompt').hidden=true;
  $('tagInstructions').textContent = 'Se a tag não for reconhecida, marque os dois extremos do diâmetro na foto. Confirme o tamanho real acima.';
  $('manualOptions').hidden = true; $('dropzone').classList.remove('marking');
  busy(true, 'Preparando sua foto', 'Organizando a orientação e a prévia da imagem.'); notice('');
  try {
    const result = libraryName ? await api('/api/library', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:libraryName})}) : await api('/api/upload', {method: 'POST', headers: {'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name)}, body: file});
    const image = await loadImage(`/api/image/${result.id}`);
    state.id = result.id; state.name = result.name; state.image = image; state.reference=result.reference;
    $('emptyState').hidden = true; $('canvas').hidden = false; $('dropzone').classList.add('has-image');
    $('filename').textContent = `${result.name} · ${result.width} × ${result.height} px na análise`;
    $('photoHint').textContent = '↳ Confira o tamanho físico do marcador antes de estimar as medidas.';
    $('original').disabled = false; $('step2').classList.add('current'); draw();
  } catch (error) {
    state.image = null; $('canvas').hidden = true; $('emptyState').hidden = false; $('filename').textContent = 'Nenhuma foto selecionada'; notice(error.message, true);
  } finally { busy(false); $('file').value = ''; $('librarySelect').value = ''; }
}
function startManual() {
  if (!state.id || state.busy) return;
  resetReport(); state.tagging = false; state.marking = true; state.points = [];
  $('manualOptions').hidden = false; $('dropzone').classList.add('marking'); $('measureManual').disabled = true;
  $('pointInstructions').textContent = '1. Clique no centro do cotovelo na foto. Depois, clique no centro do punho. A calibração da tag será preservada.';
  $('photoHint').textContent = '↳ Marcação manual: clique primeiro no cotovelo, depois no punho.';
  $('markingPrompt').hidden=false; $('markingPrompt').textContent='PASSO 1 DE 2 · Clique no COTOVELO na foto. Não clique na tag.';
  notice('A escala foi mantida. Marque cotovelo e punho e confirme a medição.'); busy(false); draw();
  $('canvas').scrollIntoView({behavior:'smooth',block:'center'});
}
function cancelManual() { state.marking = false; state.points = []; $('manualOptions').hidden = true; $('markingPrompt').hidden=true; $('dropzone').classList.remove('marking'); notice(''); busy(false); draw(); }
async function analyze(manual = false) {
  if (!state.id || state.busy || !$('form').reportValidity()) return;
  if (manual && state.points.length !== 2) return;
  const points = state.points.length === 2 ? state.points.map(p => [...p]) : null;
  let recovery = null;
  resetReport(); state.marking = false; state.tagging = false; $('dropzone').classList.remove('marking');
  busy(true); notice('');
  try {
    await api('/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: state.id, method: $('method').value, size: Number($('size').value), slice: Number($('slice').value), markerId: Number($('markerId').value), side: $('side').value, points, tagPoints: state.tagPoints.length === 2 ? state.tagPoints : null})});
    const deadline = Date.now() + 10 * 60 * 1000;
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 900));
      const result = await api(`/api/status/${state.id}`);
      if (result.state === 'error') { const error=Error(result.error); error.code=result.error_code; throw error; }
      if (result.state === 'done') { state.report = result.report; break; }
      if (Date.now() > deadline) throw Error('A análise está demorando mais que o esperado. Aguarde e atualize a página antes de tentar novamente.');
    }
    $('manualOptions').hidden = true; $('results').hidden = false;
    $('download').href = `/api/export/${state.id}`;
    const arms = state.report.bracos;
    $('resultContent').hidden = !arms.length;
    $('armSelect').replaceChildren(...arms.map((arm, i) => new Option(`Segmento ${i + 1} · ${arm.lado}`, i)));
    if (arms.length) {
      $('recovery').hidden=true; $('markingPrompt').hidden=true; state.recovery=null;
      await showArm(0); $('step3').classList.add('current');
      $('photoHint').textContent = '↳ Confira os limites coloridos. Use a marcação manual se precisar ajustar cotovelo ou punho.';
      notice('Estimativa concluída. Revise o segmento colorido antes de usar ou exportar os valores.');
    } else {
      $('conversionText').textContent = 'Sem escala ou segmento validado nesta tentativa. Use a calibração do marcador por dois cliques e, se necessário, marque cotovelo e punho.';
      $('geometryText').textContent = '';
      state.view = 'original'; quality(state.report.flags); draw();
      recovery = state.report.acao_necessaria || (state.report.calibracao.homografia_processada_mm ? 'marcar_braco' : 'calibrar_marcador');
      notice(recovery==='marcar_braco' ? 'A tag foi calibrada. Falta delimitar cotovelo e punho; continue na foto.' : 'Falta definir a referência física. Continue pela marcação ampliada da tag.');
    }
    if (!recovery) $('results').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest'});
  } catch (error) {
    notice(error.message, true); state.view = 'original'; draw();
    if(error.code==='DIAMETRO_TAG_INCOMPATIVEL') { state.tagPoints=[]; recovery='calibrar_marcador'; }
  }
  finally { busy(false); if(recovery) guideRecovery(recovery); }
}

function guideRecovery(action) {
  state.recovery=action; $('recovery').hidden=false;
  $('recoveryTitle').textContent=action==='marcar_braco' ? 'Falta apenas confirmar os limites do braço' : 'Vamos definir a escala do adesivo';
  $('recoveryText').textContent=action==='marcar_braco' ? 'A calibração foi preservada. Clique no cotovelo e depois no punho na imagem; confirme para calcular as seções.' : 'A marcação do diâmetro acontece em uma janela ampliada. Ela é diferente dos dois pontos do braço.';
  $('continueRecovery').textContent=action==='marcar_braco' ? 'Continuar marcando cotovelo e punho →' : 'Abrir o marcador ampliado →';
  if(action==='marcar_braco') startManual();
  else startTagCalibration();
}

function setTagCrop(center=null) {
  const image=state.image;
  if(!center) { state.tagCrop={x:0,y:0,w:image.naturalWidth,h:image.naturalHeight}; state.tagPhase='center'; }
  else {
    const diameter=state.reference ? Math.max(...state.reference.axes) : 60;
    const side=Math.min(Math.max(160,diameter*4),Math.min(image.naturalWidth,image.naturalHeight));
    state.tagCrop={x:Math.max(0,Math.min(image.naturalWidth-side,center[0]-side/2)),y:Math.max(0,Math.min(image.naturalHeight-side,center[1]-side/2)),w:side,h:side};
    state.tagPhase='diameter';
  }
  state.tagDraft=[]; $('tagApply').disabled=true;
  $('tagDialogInstruction').textContent=state.tagPhase==='center' ? 'Primeiro clique no CENTRO DO ADESIVO para ampliar. Depois você marcará duas bordas.' : 'Imagem ampliada do marcador: clique em uma borda do círculo e depois na borda oposta, passando pelo centro.';
  drawTag();
}

function drawTag() {
  const canvas=$('tagCanvas'), c=state.tagCrop;
  canvas.width=Math.round(c.w);canvas.height=Math.round(c.h);
  const context=canvas.getContext('2d');
  context.drawImage(state.image,c.x,c.y,c.w,c.h,0,0,canvas.width,canvas.height);
  const scale=canvas.width/c.w;
  context.lineWidth=Math.max(1,canvas.width/150);context.strokeStyle='#fff';context.fillStyle='#e0aa14';
  state.tagDraft.forEach(([x,y]) => {context.beginPath();context.arc((x-c.x)*scale,(y-c.y)*scale,Math.max(2,canvas.width/65),0,2*Math.PI);context.fill();context.stroke();});
  if(state.tagDraft.length===2) {
    context.beginPath();context.moveTo((state.tagDraft[0][0]-c.x)*scale,(state.tagDraft[0][1]-c.y)*scale);context.lineTo((state.tagDraft[1][0]-c.x)*scale,(state.tagDraft[1][1]-c.y)*scale);context.strokeStyle='#efb619';context.stroke();
  }
}

function startTagCalibration() {
  if(state.busy || !state.id) return;
  if($('method').value!=='circulo') { notice('Para ArUco confira o ID e a impressão do marcador.',true);return; }
  $('tagAuto').disabled=!state.reference;
  setTagCrop(state.reference?.center || null);
  if(!$('tagDialog').open) $('tagDialog').showModal();
}
function quality(flags) {
  $('qualityList').replaceChildren(...[...new Set(flags)].map(flag => { const li = document.createElement('li'); li.textContent = labels[flag] || flag.replaceAll('_', ' ').toLowerCase(); return li; }));
}
async function showArm(index) {
  const revision = state.revision;
  state.arm = index; const arm = state.report.bracos[index];
  const blocked = arm.qualidade === 'bloqueada';
  $('lengthValue').textContent = `${number(arm.comprimento_cm)} cm${blocked ? ' · bloqueado' : ' · provisório'}`;
  $('total').textContent = blocked ? '—' : number(arm.area_total_cm2); $('tableTotal').textContent = blocked ? 'Bloqueada' : `${number(arm.area_total_cm2)} cm²`;
  document.querySelector('.review-badge').textContent = blocked ? '● Medida bloqueada: máscara ou eixo inadequados' : '● Valor provisório: confira escala e limites';
  const cal = state.report.calibracao;
  $('conversionText').textContent = cal.pixels_por_cm2_processada ? `Tag informada: ${number(cal.diametro_real_mm_informado, 1)} mm. Escala na foto original: ${number(cal.px_por_mm * 10)} px/cm. Na imagem processada: ${number(cal.pixels_por_cm2_processada)} pixels por cm². Conta: ${number(arm.area_pixels, 0)} pixels ÷ ${number(cal.pixels_por_cm2_processada)} = ${number(arm.area_total_cm2)} cm² (${blocked ? 'diagnóstico bloqueado, não usar como medida' : 'provisório'}).` : 'ArUco: a escala varia pela imagem. A área é integrada pela homografia, sem um fator único de pixels por cm².';
  $('geometryText').textContent = `Segmento delimitado: ${number(arm.comprimento_cm)} cm. Cobertura longitudinal da máscara: ${number(arm.cobertura_longitudinal * 100, 1)}%. Contornos brancos: limites medidos; S01, S02… correspondem às linhas da tabela. Amarelo: marcador usado na escala.`;
  $('sliceRows').replaceChildren(...arm.fatias.map((slice, i) => {
    const tr = document.createElement('tr');
    const extent = slice.fim_cm - slice.inicio_cm;
    for (const value of [`S${String(i + 1).padStart(2, '0')}`, `${number(slice.inicio_cm, 1)} – ${number(slice.fim_cm, 1)}`, blocked ? `${number(slice.area_pixels, 0)} px · bloqueada` : `${number(slice.area_cm2)} cm² · ${number(slice.area_pixels, 0)} px`, blocked || extent <= 0 ? '—' : `${number(slice.area_cm2 / extent)} cm`]) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
    return tr;
  }));
  const first = arm.fatias[0];
  $('unitExplanation').textContent = first ? `Como ler S01: a região entre ${number(first.inicio_cm,1)} e ${number(first.fim_cm,1)} cm ao longo do eixo tem ${number(first.area_cm2)} cm² de área projetada estimada. Esse valor não é circunferência. A largura média é área ÷ comprimento da seção, um diagnóstico dependente da escala e da máscara.` : 'O programa não mede circunferência.';
  quality([...state.report.flags, ...arm.flags]);
  const image = await loadImage(`/api/image/${state.id}/${index}?t=${Date.now()}`);
  if (state.arm !== index || revision !== state.revision) return;
  state.overlay = image; state.view = 'overlay'; $('overlay').disabled = false; $('zoom').disabled = false; draw();
}
$('choose').addEventListener('click', () => $('file').click()); $('replace').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', event => upload(event.target.files[0]));
$('librarySelect').addEventListener('change', event => { if(event.target.value) upload(null,event.target.value); });
for (const name of ['dragenter', 'dragover']) $('dropzone').addEventListener(name, event => { event.preventDefault(); if (!state.busy) $('dropzone').classList.add('dragover'); });
for (const name of ['dragleave', 'drop']) $('dropzone').addEventListener(name, event => { event.preventDefault(); $('dropzone').classList.remove('dragover'); });
$('dropzone').addEventListener('drop', event => upload(event.dataTransfer.files[0]));
window.addEventListener('dragover', event => event.preventDefault()); window.addEventListener('drop', event => event.preventDefault());
$('form').addEventListener('submit', event => { event.preventDefault(); analyze(); });
$('manual').addEventListener('click', startManual); $('cancelManual').addEventListener('click', cancelManual); $('measureManual').addEventListener('click', () => analyze(true));
$('method').addEventListener('change', () => { state.tagPoints = []; state.tagging = false; const aruco = $('method').value === 'aruco'; $('size').value = aruco ? 40 : 19; $('sizeLabel').textContent = aruco ? 'Lado do quadrado' : 'Diâmetro real'; $('arucoField').hidden = !aruco; });
$('form').addEventListener('change', () => { if (state.report) notice('Configuração alterada. Analise novamente para aplicar os novos parâmetros. O relatório anterior conserva os parâmetros usados.'); });
$('canvas').addEventListener('click', event => {
  if (state.tagging && !state.busy) {
    const rect = $('canvas').getBoundingClientRect();
    state.tagPoints.push([(event.clientX - rect.left) * $('canvas').width / rect.width, (event.clientY - rect.top) * $('canvas').height / rect.height]);
    draw();
    if (state.tagPoints.length === 2) {
      state.tagging = false;
      $('tagInstructions').textContent = 'Diâmetro marcado. Confirme o tamanho real e clique em Estimar medidas. Para close-up, marque também cotovelo e punho.';
      notice('Calibração manual pronta. Os pontos serão usados na próxima análise. Para corrigir, clique novamente em Calibrar marcador.');
    } else $('tagInstructions').textContent = 'Agora clique na borda oposta do marcador, passando pelo centro do círculo.';
    return;
  }
  if (!state.marking || state.busy || state.points.length >= 2) return;
  const rect = $('canvas').getBoundingClientRect();
  state.points.push([(event.clientX - rect.left) * $('canvas').width / rect.width, (event.clientY - rect.top) * $('canvas').height / rect.height]);
  $('pointInstructions').textContent = state.points.length === 1 ? 'Cotovelo marcado. Agora clique no centro do punho.' : 'Pontos marcados. Confirme o lado e clique em “Medir segmento marcado”. Para refazer, use “Marcar pontos na imagem”.';
  $('markingPrompt').textContent=state.points.length===1 ? 'PASSO 2 DE 2 · Agora clique no PUNHO.' : 'Dois pontos marcados. Clique em “Medir com os dois pontos” para calcular.';
  $('measureManual').disabled = state.points.length !== 2; busy(false); draw();
});
$('original').addEventListener('click', () => { if (!state.busy) { state.view = 'original'; draw(); } });
$('overlay').addEventListener('click', () => { if (!state.busy) { state.view = 'overlay'; draw(); } });
$('armSelect').addEventListener('change', () => showArm(Number($('armSelect').value)).catch(error => notice(error.message, true)));
$('zoom').addEventListener('click', () => { if (state.overlay) { $('zoomImage').src = state.overlay.src; $('zoomDialog').showModal(); } });
$('markTag').addEventListener('click', startTagCalibration);
$('continueRecovery').addEventListener('click', () => state.recovery==='marcar_braco' ? startManual() : startTagCalibration());
$('tagCancel').addEventListener('click', () => $('tagDialog').close());
$('tagReset').addEventListener('click', () => setTagCrop(state.reference?.center || null));
$('tagAuto').addEventListener('click', () => {state.tagPoints=[];$('tagDialog').close();$('tagInstructions').textContent='Marcador automático selecionado. Os pontos do braço são definidos separadamente.';analyze();});
$('tagCanvas').addEventListener('click', event => {
  const canvas=$('tagCanvas'),rect=canvas.getBoundingClientRect(),c=state.tagCrop;
  const point=[c.x+(event.clientX-rect.left)*c.w/rect.width,c.y+(event.clientY-rect.top)*c.h/rect.height];
  if(state.tagPhase==='center') {setTagCrop(point);return;}
  if(state.tagDraft.length===2) state.tagDraft=[];
  state.tagDraft.push(point);drawTag();
  if(state.tagDraft.length===1) { $('tagDialogInstruction').textContent='Primeira borda marcada. Agora clique na borda oposta do adesivo.'; $('tagApply').disabled=true;return; }
  const diameter=Math.hypot(state.tagDraft[1][0]-state.tagDraft[0][0],state.tagDraft[1][1]-state.tagDraft[0][1]);
  const expected=state.reference ? Math.sqrt(state.reference.axes[0]*state.reference.axes[1]) : null;
  const valid=diameter>=8 && (!expected || (diameter/expected>=.55 && diameter/expected<=1.8));
  $('tagApply').disabled=!valid;
  $('tagDialogInstruction').textContent=valid ? `Diâmetro marcado: ${number(diameter,1)} pixels. Dimensão física informada: ${$('size').value} mm. Confira as bordas e continue.` : 'A linha não corresponde ao diâmetro do adesivo. Clique em Refazer marcação ou use o marcador detectado.';
});
$('tagApply').addEventListener('click', () => {
  if($('tagApply').disabled || state.tagDraft.length!==2) return;
  state.tagPoints=state.tagDraft.map(p=>[...p]);$('tagDialog').close();
  $('tagInstructions').textContent='Diâmetro da tag confirmado. Cotovelo e punho serão tratados em uma etapa separada.';
  analyze();
});
$('closeZoom').addEventListener('click', () => $('zoomDialog').close());
busy(false);
api('/api/config').then(data => {
  if (data.app !== 'projeto-fisio-local' || !data.atualizado) throw Error('O serviço aberto é antigo. Execute novamente Abrir Fisio.cmd e use a nova aba que ele abrir. Não é necessário manter o VS Code aberto.');
  state.token = data.token; state.ready = true;
  $('connectionStatus').textContent = 'Serviço atualizado · conectado';
  $('connectionStatus').title = `Versão ${data.versao} · ${data.python}`;
  $('librarySelect').append(...data.imagens.map(name => new Option(name,name)));
  busy(false);
}).catch(error => {
  state.ready = false; busy(false);
  $('connectionStatus').textContent = 'Serviço precisa ser reiniciado'; $('connectionStatus').classList.add('disconnected');
  notice(error.message.includes('antigo') ? error.message : 'Não foi possível conectar ao serviço local. Execute Abrir Fisio.cmd e use a aba aberta por ele.',true);
});
