// === GuíaIA - Pregunta por pregunta con validación contextual ===

const chat = document.querySelector('#chat');
const input = document.querySelector('#input');
const btn = document.querySelector('#boton-enviar');

let questions = [];
let idx = 0;
let answers = {};  // acumulado
let fase = "preguntas"; // preguntas -> resultado

function burUser(t){ const p=document.createElement('p'); p.className='chat__burbuja chat__burbuja--usuario'; p.textContent=t; chat.appendChild(p); }
function burBot(html){ const p=document.createElement('p'); p.className='chat__burbuja chat__burbuja--bot'; p.innerHTML=html; chat.appendChild(p); return p; }
function scroll(){ chat.scrollTop = chat.scrollHeight; }

async function getJSON(url){ const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function postJSON(url, body){ const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}); if(!r.ok) throw new Error(await r.text()); return r.json(); }

async function init(){
  const q = await getJSON('/questions');
  questions = q.questions || [];
  answers = {}; idx = 0; fase = "preguntas";
  burBot("¡Hola! Soy <b>GuíaIA</b>. Te haré preguntas secuenciales. Cada respuesta debe ser coherente con las anteriores.");
  ask();
}

function ask(){
  const q = questions[idx];
  input.value = "";                           // <-- limpia SIEMPRE al mostrar la siguiente
  input.placeholder = q ? "Escribe tu respuesta…" : "";
  if (q) burBot(`<b>Pregunta ${idx+1}/${questions.length}:</b> ${q.label}`);
  scroll();
}

async function enviar(){
  const val = (input.value || "").trim();
  if (!val || fase !== "preguntas") return;

  const q = questions[idx];
  burUser(val);                               // si quieres ver tu respuesta como burbuja
  input.value = "";                           // <-- limpia INMEDIATAMENTE
  input.placeholder = "Validando…";           // feedback visual rápido

  const thinking = burBot("Validando…");

  try {
    const v = await postJSON('/validate-step', {
      question_id: q.id,
      answer: val,
      history: answers
    });

    if (!v.ok){
      thinking.innerHTML = `❌ <b>No pasa validación:</b> ${v.hint}<br><i>Por favor, responde de nuevo esta pregunta.</i>`;
      // ANALYTICS: registrar error de validación como "wrong_answer"
      try { if (typeof window.onWrongAnswer === "function") window.onWrongAnswer(); } catch {}
      input.placeholder = "Escribe tu respuesta…";
      input.focus();
      scroll();
      return;
    }

    // OK: guardar y avanzar
    answers[q.id] = val;
    thinking.innerHTML = "✅ Ok. Registrado.";
    idx++;

    if (idx < questions.length){
      ask();                                   // pregunta siguiente (input limpio)
    } else {
      await composeAndScore();
      fase = "resultado";
    }
  } catch(e){
    thinking.textContent = "Error de validación: " + e.message;
    // ANALYTICS: también puedes considerarlo wrong_answer, si así lo prefieres
    try { if (typeof window.onWrongAnswer === "function") window.onWrongAnswer(); } catch {}
  } finally {
    if (fase === "preguntas") input.placeholder = "Escribe tu respuesta…";
    scroll();
  }
}


async function composeAndScore(){
  const p1 = burBot("Construyendo prompt inicial…");
  const comp = await postJSON('/compose-initial', { answers_clean: answers });
  const prompt = comp.prompt || "(sin prompt)";
  p1.innerHTML = "<b>Prompt inicial:</b><br>" + prompt.replace(/\n/g,"<br>");

  // ANALYTICS: enviar el evento "prompt_created" UNA sola vez por sesión
  try {
    if (!window.__firstPromptLogged && typeof window.onFirstPromptCreated === "function") {
      // Enviamos tanto el texto del prompt como las respuestas crudas y el esquema de preguntas
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
  const sc = await postJSON('/scorecard', { prompt });
  const c = sc.criteria || {};
  p2.innerHTML = `<b>Scorecard:</b> ${sc.total}/${sc.max}<br>` +
    `rol=${c.rol??0}, objetivo=${c.objetivo??0}, ` +
    `tono=${c.tono??0}, formato=${c.formato??0}, ` +
    `longitud=${c.longitud??0}, calidad=${c.calidad??0}`;

  // --- NUEVO: guardar prompt + mostrar botones una sola vez
  window.currentPromptText = prompt;
  renderActionButtonsOnce();
}

btn.addEventListener('click', enviar);
input.addEventListener('keyup', e => { if (e.key === 'Enter') enviar(); });

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

  // 1) Reiniciar todo el flujo
  btnNew.addEventListener('click', async () => {
    // ANALYTICS: "nuevo prompt"
    try { if (typeof window.onNewPromptClick === "function") window.onNewPromptClick(); } catch {}
    chat.innerHTML = "";
    input.value = "";
    questions = []; idx = 0; answers = {}; fase = "preguntas";
    await init(); // vuelve a preguntar desde cero
  });

  // 2) Mejorar con IA (usa el último prompt compuesto)
  btnImprove.addEventListener('click', async () => {
    // ANALYTICS: "improve_click"
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
      scroll();
      renderPostImproveButtonsOnce(improved);
    }catch(e){
      burBot("⚠️ No se pudo mejorar el prompt: " + esc(e.message));
      scroll();
      // ANALYTICS opcional: también podrías registrar wrong_answer aquí
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
    // solo actualiza el texto guardado si ya existen
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

  // 1) Reiniciar flujo
  btnNew2.addEventListener('click', async () => {
    // ANALYTICS: "nuevo prompt"
    try { if (typeof window.onNewPromptClick === "function") window.onNewPromptClick(); } catch {}
    chat.innerHTML = "";
    input.value = "";
    questions = []; idx = 0; answers = {}; fase = "preguntas";
    await init();
  });

  // 2) Copiar en portapapeles
  btnCopy.addEventListener('click', async () => {
    const txt = getPrompt();
    if (!txt) { alert("No hay prompt mejorado para copiar."); return; }
    const ok = await copyToClipboard(txt);
    burBot(ok ? "✅ Prompt copiado al portapapeles." : "⚠️ No se pudo copiar. Copia manualmente.");
    scroll();
    // ANALYTICS: "clipboard_copy"
    try { if (typeof window.onClipboardCopy === "function") window.onClipboardCopy(); } catch {}
  });
}
