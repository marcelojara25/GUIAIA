// === GuíaIA - Pregunta por pregunta con validación contextual ===

// DOM
const chat  = document.getElementById('chat');
const input = document.getElementById('input');
const btn   = document.getElementById('boton-enviar');

// Estado
let questions = [];
let idx = 0;
let answers = {};            // respuestas acumuladas
let fase = "preguntas";      // preguntas -> resultado

// Helpers de burbujas
function burUser(t) {
  const p = document.createElement('p');
  p.className = 'chat__burbuja chat__burbuja--usuario';
  p.textContent = t;
  chat.appendChild(p);
}
function burBot(html) {
  const p = document.createElement('p');
  p.className = 'chat__burbuja chat__burbuja--bot';
  p.innerHTML = html;
  chat.appendChild(p);
  return p;
}

// Fetch helpers
async function getJSON(url){
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function postJSON(url, body){
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ===== Auto-scroll robusto =====
function scrollElToBottom(el, { smooth = true } = {}) {
  if (!el) return;
  const behavior = smooth ? 'smooth' : 'auto';
  requestAnimationFrame(() => {
    el.scrollTo({ top: el.scrollHeight, behavior });
    // Fallback WebKit
    setTimeout(() => { el.scrollTop = el.scrollHeight; }, 0);
  });
}
function scrollChatToBottom(opts = {}) {
  if (!chat) return;
  const chatIsScrollable = chat.scrollHeight > chat.clientHeight + 1;
  if (chatIsScrollable) {
    scrollElToBottom(chat, opts);
  } else {
    // Si quien scrollea es el documento (layout muy alto)
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
      setTimeout(() => { document.documentElement.scrollTop = document.documentElement.scrollHeight; }, 0);
    });
  }
}
// Observa inserciones (del bot o del usuario)
if (chat) {
  const observer = new MutationObserver(muts => {
    for (const m of muts) {
      if (m.type === 'childList' && m.addedNodes.length) {
        scrollChatToBottom();
        break;
      }
    }
  });
  observer.observe(chat, { childList: true, subtree: true });
}
// Eventos extra
window.addEventListener('load',   () => scrollChatToBottom({ smooth:false }));
window.addEventListener('resize', () => scrollChatToBottom({ smooth:false }));
chat?.addEventListener('load', e => {
  if (e.target && e.target.tagName === 'IMG') scrollChatToBottom();
}, true);
// Exponer por si quieres llamarlo manualmente
window.scrollChatToBottom = scrollChatToBottom;

// Inicio
async function init(){
  const q = await getJSON('/questions');
  questions = q.questions || [];
  answers = {}; idx = 0; fase = "preguntas";
  burBot("¡Hola! Soy <b>GuíaIA</b>. Te haré preguntas secuenciales. Cada respuesta debe ser coherente con las anteriores.");
  ask();
}

// Mostrar siguiente pregunta
function ask(){
  const q = questions[idx];
  input.value = "";                                      // limpia SIEMPRE
  input.placeholder = q ? "Escribe tu respuesta…" : "";
  if (q) burBot(`<b>Pregunta ${idx+1}/${questions.length}:</b> ${q.label}`);
  scrollChatToBottom();
}

// Enviar respuesta
async function enviar(){
  const val = (input.value || "").trim();
  if (!val || fase !== "preguntas") return;

  const q = questions[idx];
  burUser(val);
  input.value = "";
  input.placeholder = "Validando…";

  const thinking = burBot("Validando…");
  scrollChatToBottom();

  try {
    const v = await postJSON('/validate-step', {
      question_id: q.id,
      answer: val,
      history: answers
    });

    if (!v.ok){
      thinking.innerHTML = `❌ <b>No pasa validación:</b> ${v.hint}<br><i>Por favor, responde de nuevo esta pregunta.</i>`;
      try { if (typeof window.onWrongAnswer === "function") window.onWrongAnswer(); } catch {}
      input.placeholder = "Escribe tu respuesta…";
      input.focus();
      scrollChatToBottom();
      return;
    }

    // OK
    answers[q.id] = val;
    thinking.innerHTML = "✅ Ok. Registrado.";
    idx++;

    if (idx < questions.length){
      ask();
    } else {
      await composeAndScore();
      fase = "resultado";
    }
  } catch(e){
    thinking.textContent = "Error de validación: " + e.message;
    try { if (typeof window.onWrongAnswer === "function") window.onWrongAnswer(); } catch {}
  } finally {
    if (fase === "preguntas") input.placeholder = "Escribe tu respuesta…";
    scrollChatToBottom();
  }
}

// Composición y score
async function composeAndScore(){
  const p1 = burBot("Construyendo prompt inicial…");
  scrollChatToBottom();

  const comp = await postJSON('/compose-initial', { answers_clean: answers });
  const prompt = comp.prompt || "(sin prompt)";
  p1.innerHTML = "<b>Prompt inicial:</b><br>" + prompt.replace(/\n/g,"<br>");

  // Analytics: prompt_created (solo una vez)
  try {
    if (!window.__firstPromptLogged && typeof window.onFirstPromptCreated === "function") {
      const payload = {
        prompt_text: prompt,
        answers: {...answers},
        questions: (questions || []).map(q => ({ id: q.id, label: q.label }))
      };
      window.onFirstPromptCreated(payload);
      window.__firstPromptLogged = true;
    }
  } catch {}

  const p2 = burBot("Calculando Scorecard…");
  scrollChatToBottom();

  const sc = await postJSON('/scorecard', { prompt });
  const c = sc.criteria || {};
  p2.innerHTML = `<b>Scorecard:</b> ${sc.total}/${sc.max}<br>` +
    `rol=${c.rol??0}, objetivo=${c.objetivo??0}, ` +
    `tono=${c.tono??0}, formato=${c.formato??0}, ` +
    `longitud=${c.longitud??0}, calidad=${c.calidad??0}`;

  window.currentPromptText = prompt;
  renderActionButtonsOnce();
  scrollChatToBottom();
}

// Eventos de UI
btn.addEventListener('click', enviar);
input.addEventListener('keyup', e => { if (e.key === 'Enter') enviar(); });

// Inicia la app
init();


// ================== BOTONES POST-SCORE ==================
function renderActionButtonsOnce(){
  if (document.getElementById('actionsRow')) return; // evita duplicados

  const sec = document.createElement('section');
  sec.id = 'actionsRow';
  sec.className = 'container';
  sec.style.marginTop = '12px';
  sec.innerHTML = `
    <div style="display:flex; gap:10px; flex-wrap:wrap;">
      <button id="btn-new" class="btn btn-secondary">Iniciar otro prompt</button>
      <button id="btn-improve" class="btn btn-primary">Mejorar con IA</button>
    </div>
  `;
  chat.appendChild(sec);

  const btnNew = document.getElementById('btn-new');
  const btnImprove = document.getElementById('btn-improve');

  function esc(s){ return (s||"").replace(/[&<>]/g, m=>({ "&":"&amp;","<":"&lt;",">":"&gt;" }[m])); }

  // Reiniciar
  btnNew.addEventListener('click', async () => {
    try { if (typeof window.onNewPromptClick === "function") window.onNewPromptClick(); } catch {}
    chat.innerHTML = "";
    input.value = "";
    questions = []; idx = 0; answers = {}; fase = "preguntas";
    await init();
    scrollChatToBottom();
  });

  // Mejorar con IA
  btnImprove.addEventListener('click', async () => {
    try { if (typeof window.onImproveClick === "function") window.onImproveClick(); } catch {}

    const basePrompt = (window.currentPromptText || "").trim();
    if (!basePrompt){
      alert("Primero genera un prompt inicial.");
      return;
    }
    const old = btnImprove.textContent;
    btnImprove.disabled = true; btnImprove.textContent = "Mejorando...";

    try{
      const data = await postJSON('/improve-online', { prompt: basePrompt });
      if (data.error) throw new Error(data.error);
      const improved = (data.prompt || "").trim();
      burBot(`<b>Prompt mejorado (≤150 palabras):</b><br><pre style="white-space:pre-wrap;margin:0">${esc(improved)}</pre>`);
      scrollChatToBottom();
      renderPostImproveButtonsOnce(improved);
    }catch(e){
      burBot("⚠️ No se pudo mejorar el prompt: " + esc(e.message));
      scrollChatToBottom();
      try { if (typeof window.onWrongAnswer === "function") window.onWrongAnswer(); } catch {}
    }finally{
      btnImprove.disabled = false; btnImprove.textContent = old;
    }
  });
}

// =============== BOTONES POST-MEJORA (2 botones) ===============
function renderPostImproveButtonsOnce(improvedText){
  const row1 = document.getElementById('actionsRow');
  if (row1) row1.style.display = 'none';

  const EXISTING = document.getElementById('postImproveRow');
  if (EXISTING) {
    EXISTING.dataset.prompt = improvedText || "";
    return;
  }

  const sec = document.createElement('section');
  sec.id = 'postImproveRow';
  sec.className = 'container';
  sec.style.marginTop = '10px';
  sec.dataset.prompt = improvedText || "";
  sec.innerHTML = `
    <div style="display:flex; gap:10px; flex-wrap:wrap;">
      <button id="btn-new-2" class="btn btn-secondary">Iniciar otro prompt</button>
      <button id="btn-copy"  class="btn btn-primary">Copiar en portapapeles</button>
    </div>
  `;
  chat.appendChild(sec);

  const $sec     = document.getElementById('postImproveRow');
  const btnNew2  = document.getElementById('btn-new-2');
  const btnCopy  = document.getElementById('btn-copy');

  const getPrompt = () => ($sec.dataset.prompt || "").trim();

  async function copyToClipboard(text){
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position='fixed'; ta.style.opacity='0';
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
        return true;
      } catch { return false; }
    }
  }

  // Reiniciar flujo
  btnNew2.addEventListener('click', async () => {
    try { if (typeof window.onNewPromptClick === "function") window.onNewPromptClick(); } catch {}
    chat.innerHTML = "";
    input.value = "";
    questions = []; idx = 0; answers = {}; fase = "preguntas";
    await init();
    scrollChatToBottom();
  });

  // Copiar
  btnCopy.addEventListener('click', async () => {
    const txt = getPrompt();
    if (!txt) { alert("No hay prompt mejorado para copiar."); return; }
    const ok = await copyToClipboard(txt);
    burBot(ok ? "✅ Prompt copiado al portapapeles." : "⚠️ No se pudo copiar. Copia manualmente.");
    scrollChatToBottom();
    try { if (typeof window.onClipboardCopy === "function") window.onClipboardCopy(); } catch {}
  });
}
