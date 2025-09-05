print(">>> running:", __file__)
import os; print(">>> cwd:", os.getcwd())

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os, re, json, traceback
from sqlalchemy import create_engine, Column, String, Integer, BigInteger, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
import uuid
import requests
from sqlalchemy import text
from functools import wraps
from flask import session, redirect, url_for, render_template_string


# =========================
#   Config
# =========================
load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "dev")

# --- Admin key desde .env (default Bootcamp1) ---
ADMIN_KEY = os.getenv("ADMIN_KEY", "Bootcamp1")

# Decorador para proteger rutas (API y páginas)
def require_admin(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # Ya autenticado en esta sesión
        if session.get("admin_ok"):
            return view_func(*args, **kwargs)

        # Permite autenticación vía query ?key=... o header X-Admin-Key (para curl/Invoke)
        key = request.args.get("key") or request.headers.get("X-Admin-Key")
        if key == ADMIN_KEY:
            session["admin_ok"] = True
            session["fail_count"] = 0
            return view_func(*args, **kwargs)

        # Contabiliza fallos y decide redirect
        session["fail_count"] = session.get("fail_count", 0) + 1
        if session["fail_count"] >= 3:
            session.pop("fail_count", None)
            session.pop("admin_ok", None)
            # redirige a tu home
            return redirect(url_for("index"))

        # Si el cliente es navegador (HTML), redirige a login; si es API, 401 JSON
        accepts_html = "text/html" in (request.headers.get("Accept") or "")
        if accepts_html and request.method in ("GET", "HEAD"):
            return redirect(url_for("analytics_login"))
        return jsonify(ok=False, error="unauthorized"), 401
    return wrapper


# =========================
#   DB: SQLAlchemy (Postgres en Render / SQLite local)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")  # Render: postgresql+psycopg://USER:PASS@HOST:PORT/DBNAME
if not DATABASE_URL:
    # Local sin Postgres: usa SQLite para pruebas
    DATABASE_URL = "sqlite:///./dev.db"

# Crea el engine según el tipo de URL
if DATABASE_URL.startswith("postgresql"):
    # Postgres (Render o local): sí definimos pool_size y max_overflow
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
else:
    # SQLite: NO pases pool_size ni max_overflow
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass


# --- Ollama (opcional) ---
try:
    from ollama import Client as OllamaClient
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    LLM_MODEL   = os.getenv("LLM_MODEL", "mistral")
    ollama = OllamaClient(host=OLLAMA_HOST)
    _HAS_OLLAMA = True
except Exception:
    _HAS_OLLAMA = False

# --- Gemini (requerido para scorecard y fallback de validación) ---
_HAS_GENAI = False
try:
    import google.generativeai as genai  # import temprano
    # Clave: argumento -> variable global Geminiapikey -> env
    _GEMINI_KEY = (globals().get("Geminiapikey") or
                   os.getenv("GEMINI_API_KEY") or
                   os.getenv("GEMINI_APIKEY"))
    if _GEMINI_KEY:
        genai.configure(api_key=_GEMINI_KEY)
        _HAS_GENAI = True
except Exception:
    _HAS_GENAI = False

# =========================
#   Utilidades
# =========================
def _parse_llm_json(s: str):
    """Intenta parsear JSON estricto. Fallback: primer bloque {...}."""
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise ValueError("No se pudo parsear JSON desde la respuesta del modelo.")

def normalize_objective(obj: str) -> str:
    base = (obj or "").strip()
    if not base:
        return "Quiero obtener un resultado claro y útil"
    low = base.lower()
    starts_ok = low.startswith(("quiero","necesito","busco","mejorar","crear","aprender","hacer","optimizar","redactar","investigar","preparar","explicar","diseñar"))
    if not starts_ok:
        base = "Quiero " + base
    return base[0].upper() + base[1:]

def normalize_length(s: str) -> str:
    s = (s or "").strip().lower()
    if not s:
        return "300 a 500 palabras"
    m = re.fullmatch(r"(\d{2,5})", s)
    if m: return f"{m.group(1)} palabras"
    m = re.fullmatch(r"(\d{2,5})\s*palabras", s)
    if m: return f"{m.group(1)} palabras"
    m = re.fullmatch(r"(\d{2,5})\s*(a|-|–|—)\s*(\d{2,5})(\s*palabras)?", s)
    if m: return f"{m.group(1)} a {m.group(3)} palabras"
    return s

def _looks_length(s: str) -> bool:
    s = (s or "").strip().lower()
    if not s: return False
    if re.fullmatch(r"\d{2,5}", s): return True
    if re.fullmatch(r"\d{2,5}\s*palabras", s): return True
    if re.fullmatch(r"\d{2,5}\s*(a|-|–|—)\s*\d{2,5}(\s*palabras)?", s): return True
    if "longitud" in s: return True
    return False

def _as_verdict_one_word(raw: str) -> str:
    """Normaliza 'coherente'/'incoherente' de cualquier LLM."""
    v = (raw or "").strip().lower()
    for ch in [".", ":", ";", ",", "¡", "!", "¿", "?", "\"", "'"]:
        v = v.replace(ch, "")
    v = v.strip()
    if v.startswith("incoher"):
        return "incoherente"
    if v.startswith("coher"):
        return "coherente"
    return ""

def _extract_text_from_candidates(resp) -> str:
    """Concatena parts.text de candidates sin usar resp.text (evita errores)."""
    try:
        for c in getattr(resp, "candidates", []) or []:
            parts = getattr(getattr(c, "content", None), "parts", []) or []
            buf = []
            for p in parts:
                t = getattr(p, "text", None)
                if isinstance(t, str):
                    buf.append(t)
            txt = "\n".join(buf).strip()
            if txt:
                return txt
        return ""
    except Exception:
        return ""

def llm_generate(prompt: str,
                 system: str | None = None,
                 model_ollama: str | None = None,
                 model_gemini: str | None = None,
                 temperature: float = 0.2,
                 max_tokens: int = 1024) -> dict:
    """
    Generación de texto con fallback:
    - Si hay Ollama y responde, usa Ollama.
    - Si no, usa Gemini.
    Retorna: {"provider": "ollama"|"gemini", "text": "..."} o lanza excepción si no hay ningún proveedor.
    """
    p = (prompt or "").strip()
    if not p:
        return {"provider": "none", "text": ""}

    # 1) Intento con Ollama (si está instalado y accesible)
    if globals().get("_HAS_OLLAMA", False):
        try:
            # Prepend de 'system' sencillo para generate(); si usas client.chat, adáptalo a messages=[...]
            full_prompt = (f"{system}\n\n{p}" if system else p)
            res = ollama.generate(
                model=model_ollama or os.getenv("LLM_MODEL", "mistral"),
                prompt=full_prompt,
                options={"temperature": temperature},
                stream=False,
            )
            txt = (res.get("response") or "").strip()
            if txt:
                return {"provider": "ollama", "text": txt}
        except Exception:
            pass  # cae a Gemini

    # 2) Fallback con Gemini
    if not globals().get("_HAS_GENAI", False):
        raise RuntimeError("No LLM provider available: configure GEMINI_API_KEY or enable Ollama.")
    model = genai.GenerativeModel(
        model_name=model_gemini or os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash"),
        system_instruction=system or None,
        generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
    )
    resp = model.generate_content(p)
    txt = _extract_text_from_candidates(resp) or (getattr(resp, "text", "") or "").strip()
    return {"provider": "gemini", "text": txt}


# =========================
#   Modelos de Analítica
# =========================
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(String(128), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    ip_hash = Column(String(128), nullable=True)
    country = Column(String(64), nullable=True)
    city = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
    referrer = Column(String(256), nullable=True)
    user = relationship("User")

class SessionMetrics(Base):
    __tablename__ = "session_metrics"
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True)
    prompts_initial_count = Column(Integer, default=0, nullable=False)
    wrong_answer_count = Column(Integer, default=0, nullable=False)
    improve_clicks_count = Column(Integer, default=0, nullable=False)
    time_on_page_ms = Column(BigInteger, default=0, nullable=False)
    time_to_first_prompt_ms = Column(BigInteger, default=0, nullable=False)
    clipboard_copy_count = Column(Integer, default=0, nullable=False)
    new_prompt_clicks_count = Column(Integer, default=0, nullable=False)

class Prompt(Base):
    __tablename__ = "prompts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    # En Postgres usamos JSONB; en SQLite guardamos como string
    prompt_initial_json = Column(JSONB if DATABASE_URL.startswith("postgresql") else String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


# =========================
#   GeoIP (Opción B con API pública)
# =========================
GEO_TIMEOUT = float(os.getenv("GEO_TIMEOUT", "2.0"))
BOOTCAMP_MODE = os.getenv("BOOTCAMP_MODE", "0") == "1"

def resolve_geo_from_request():
    """Resuelve país/ciudad desde la IP del request usando ip-api.com."""
    if BOOTCAMP_MODE:
        # Demo estable para el bootcamp
        return {"country": "Guatemala", "city": "Ciudad de Guatemala"}

    ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
    if not ip or ip.startswith("127.") or ip in ("localhost", "::1"):
        return {"country": None, "city": None}
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city",
                         timeout=GEO_TIMEOUT)
        j = r.json()
        if j.get("status") == "success":
            return {"country": j.get("country"), "city": j.get("city")}
    except Exception:
        pass
    return {"country": None, "city": None}



# =========================
#   1) Preguntas iniciales
# =========================
INITIAL_QUESTIONS = [
    {"id": "objetivo", "label": "¿Qué quieres lograr con este prompt? (ej.: mejorar tu CV para ATS 2025, aprender a cocinar una torta, explicar fracciones a un niño)"},
    {"id": "contexto", "label": "¿Quién eres tú o para quién va la respuesta? Incluye datos relevantes (ej.: soy estudiante de 2º año; es para mi familia; público infantil; para un cliente de marketing)."},
    {"id": "tono", "label": "¿Cómo quieres que suene la respuesta? Puedes elegir o escribir uno: profesional, educativo, técnico, amigable, motivador, formal, informal."},
    {"id": "formato", "label": "¿En qué forma prefieres la respuesta? (elige o escribe): lista de pasos, texto corrido, tabla comparativa, JSON, resumen."},
    {"id": "longitud", "label": "¿Qué extensión quieres? Puedes escribir un número o un rango en palabras (ej.: 200; 300-500; 300 a 500 palabras)."},
    {"id": "criterios", "label": "¿Qué condiciones debe cumplir para considerarlo bueno? (ej.: claridad, ejemplos prácticos, español neutro, creatividad, optimizado para ATS, pasos accionables)."}
]

# --- /questions y /api/questions ---
@app.get("/questions")
@app.get("/api/questions")
def questions():
    return jsonify(questions=INITIAL_QUESTIONS)

def _get_question_text(qid: str) -> str:
    for q in INITIAL_QUESTIONS:
        if q["id"] == qid:
            return q["label"]
    return qid

# =========================
#   2) Validación por paso
# =========================
ALLOWED_TONES = {"profesional","educativo","técnico","tecnico","amigable","formal","informal","motivador"}
ALLOWED_FORMATS = {"lista","lista de pasos","pasos","tabla","tabla comparativa","json","markdown","resumen","texto corrido"}

def validate_step_rules(qid: str, answer: str, prev: dict):
    """Reglas mínimas de formato. La semántica la verifica el LLM."""
    a = (answer or "").strip()
    if not a:
        return {"ok": False, "hint": "Por favor escribe una respuesta."}

    if qid == "objetivo":
        return {"ok": True, "hint": "OK", "value": normalize_objective(a)}

    if qid == "tono":
        if a.lower() not in ALLOWED_TONES:
            return {"ok": False, "hint": f"Tono no reconocido. Usa: {', '.join(sorted(ALLOWED_TONES))}."}
        return {"ok": True, "hint": "OK"}

    if qid == "formato":
        if a.lower() not in ALLOWED_FORMATS:
            return {"ok": False, "hint": f"Formato no reconocido. Usa: {', '.join(sorted(ALLOWED_FORMATS))}."}
        return {"ok": True, "hint": "OK"}

    if qid == "longitud":
        if not _looks_length(a):
            return {"ok": False, "hint": "Indica un número o un rango en palabras. Ej.: '400' o '300-500' o '300 a 500 palabras'."}
        return {"ok": True, "hint": "OK"}

    return {"ok": True, "hint": "OK"}

_LLM_DRIFT_SYSTEM_CRITERIA = (
    "Eres un clasificador en ESPAÑOL. Responde EXACTAMENTE con una sola palabra: "
    "'coherente' si la RESPUESTA enumera criterios de calidad, requisitos o condiciones "
    "aplicables al OBJETIVO (p. ej., claridad, ejemplos prácticos, precisión, español neutro, "
    "pasos accionables), aunque sean genéricos o no repitan el objetivo; "
    "'incoherente' si propone un nuevo objetivo/tema o no expresa criterios verificables. "
    "No des explicaciones."
)

_LLM_COHERENCE_SYSTEM_CRITERIA = (
    "Eres un validador en ESPAÑOL. Responde EXACTAMENTE con una sola palabra: "
    "'coherente' si la RESPUESTA describe criterios de calidad aplicables al OBJETIVO "
    "y no contradice el historial. Acepta variantes en singular/plural y ortografía aproximada "
    "(p. ej., 'ejemplo practico' ≈ 'ejemplos prácticos'). "
    "'incoherente' si no son criterios, cambian de tema o contradicen el objetivo. No des explicaciones."
)

_LLM_COHERENCE_SYSTEM_CONTEXT = (
    "Eres un validador en ESPAÑOL. Responde EXACTAMENTE con una sola palabra: "
    "'coherente' si la RESPUESTA aporta datos de perfil o audiencia (edad, país, rol, nivel, "
    "intereses o preferencias) compatibles con el OBJETIVO aunque no lo repita; "
    "'incoherente' si es claramente off-topic o contradictorio. No des explicaciones."
)

def _gemini_one_word(system_msg: str, user_msg: str) -> str:
    if not _HAS_GENAI:
        return "coherente"
    llm = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_VALIDATOR_MODEL", "gemini-1.5-flash"),
        system_instruction=system_msg,
        generation_config={"temperature": 0.2, "max_output_tokens": 8},
        safety_settings=[
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUAL", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    )
    resp = llm.generate_content(user_msg)
    text = _extract_text_from_candidates(resp)
    return _as_verdict_one_word(text)

def _validate_step_core(qid: str, answer: str, history: dict):
    # 1) Reglas mínimas (rápidas). Si falla, 200 con mensaje amable + sugerencias.
    res = validate_step_rules(qid, answer, history)
    if not res.get("ok", False):
        payload = {"ok": False, "hint": res.get("hint", "Respuesta inválida. Intenta de nuevo.")}
        if qid == "tono":
            payload["suggestions"] = sorted(ALLOWED_TONES)
        if qid == "formato":
            payload["suggestions"] = sorted(ALLOWED_FORMATS)
        return payload, 200

    # 2) Validación con LLM según tipo de pregunta
    objetivo = history.get("objetivo", "")
    question_text = _get_question_text(qid)

    if qid == "criterios":
        # (a) Drift permisivo específico para criterios
        drift_user = (
            f"OBJETIVO: {objetivo}\n"
            f"RESPUESTA: {answer}\n"
            "Responde solo: coherente | incoherente"
        )
        v_a = _gemini_one_word(_LLM_DRIFT_SYSTEM_CRITERIA, drift_user)
        if v_a == "incoherente":
            return {
                "ok": False,
                "hint": "Escribe criterios de calidad aplicables al objetivo (p. ej., claridad, "
                        "ejemplos prácticos, español neutro, precisión, pasos accionables) e intenta de nuevo."
            }, 200

        # (b) Coherencia específica para criterios
        coh_user = (
            f"TIPO_PREGUNTA: {qid}\n"
            f"OBJETIVO: {objetivo}\n"
            f"CONTEXTO: {history}\n"
            f"PREGUNTA: {question_text}\n"
            f"RESPUESTA: {answer}\n"
            "Responde solo: coherente | incoherente"
        )
        v_b = _gemini_one_word(_LLM_COHERENCE_SYSTEM_CRITERIA, coh_user)
        if v_b != "coherente":
            return {
                "ok": False,
                "hint": "No parece un criterio de calidad para este objetivo. Ejemplos: claridad, "
                        "pasos accionables, ejemplos prácticos, precisión, evitar jerga, fuentes confiables."
            }, 200

        return {"ok": True, "hint": "OK"}, 200

    elif qid == "contexto":
        # Coherencia permisiva de contexto
        coh_user = (
            f"TIPO_PREGUNTA: {qid}\n"
            f"OBJETIVO: {objetivo}\n"
            f"CONTEXTO: {history}\n"
            f"PREGUNTA: {question_text}\n"
            f"RESPUESTA: {answer}\n"
            "Responde solo: coherente | incoherente"
        )
        v_b = _gemini_one_word(_LLM_COHERENCE_SYSTEM_CONTEXT, coh_user)
        if v_b != "coherente":
            return {
                "ok": False,
                "hint": "No guarda relación con el contexto. Intenta de nuevo."
            }, 200

        return {"ok": True, "hint": "OK"}, 200

    # ✅ Para objetivo, tono, formato, longitud: ya pasaron reglas mínimas.
    return {"ok": True, "hint": "OK"}, 200



# --- /validate-step y /api/validate-step (GET y POST) ---
@app.route("/validate-step", methods=["GET", "POST"])
@app.route("/api/validate-step", methods=["GET", "POST"])
def validate_step():
    try:
        if request.method == "GET":
            qid = request.args.get("question_id") or request.args.get("qid")
            answer = (request.args.get("answer") or "").strip()
            history_raw = request.args.get("history") or "{}"
            try:
                history = json.loads(history_raw)
            except Exception:
                history = {}
        else:
            data = request.get_json(silent=True) or {}
            qid = data.get("question_id") or data.get("qid")
            answer = (data.get("answer", "") or "").strip()
            history = data.get("history") or data.get("answers_so_far") or {}

        if not qid:
            return jsonify({"ok": False, "hint": "Falta 'question_id'."}), 400

        res, code = _validate_step_core(qid, answer, history)
        return jsonify(res), code
    except Exception as e:
        return jsonify({"ok": False, "hint": f"Error interno: {e}"}), 500

# =========================
#   3) Componer prompt
# =========================
def compose_from_template(answers: dict) -> str:
    template = (
        "Actúa como asesor {tono}.\n"
        "Objetivo: {objetivo}.\n"
        "Contexto: {contexto}.\n"
        "Tono: {tono}.\n"
        "Formato de salida: {formato}.\n"
        "Longitud esperada: {longitud}.\n"
        "Criterios de calidad: {criterios}."
    )
    return template.format(
        objetivo=normalize_objective(answers.get("objetivo", "Mejorar mi CV")),
        contexto=answers.get("contexto", "Usuario general"),
        tono=answers.get("tono", "profesional"),
        formato=answers.get("formato", "lista de pasos"),
        longitud=normalize_length(answers.get("longitud", "300 a 500 palabras")),
        criterios=answers.get("criterios", "claridad, concisión, acción concreta"),
    )

# --- /compose-initial y /api/compose-initial ---
@app.post("/compose-initial")
@app.post("/api/compose-initial")
def compose_initial():
    data = request.get_json(silent=True) or {}
    answers_clean = data.get("answers_clean") or data.get("answers") or {}
    prompt = compose_from_template(answers_clean)
    return jsonify(prompt=prompt), 200

# =========================
#   4) Scorecard (Gemini)
# =========================
def _configure_genai(api_key: str | None = None):
    key = api_key or globals().get("Geminiapikey") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_APIKEY")
    if not key:
        raise RuntimeError("No se encontró la API key. Define Geminiapikey o exporta GEMINI_API_KEY.")
    genai.configure(api_key=key)

# --- Sistema estricto (igual al notebook) ---
_SCORECARD_SYSTEM_STRICT = """
Eres un evaluador técnico implacable. NO eres amable. Puntúa de 0–5 cada eje y justifica con evidencia textual.
Si no hay evidencia explícita, puntúa 0–2.

Ejes a evaluar del PROMPT (no del output del modelo):
1) Rol: especifica claramente el rol y tareas del asistente; incluye límites y exclusiones.
2) Objetivo: objetivo observable/medible; evita vaguedad.
3) Tono: instruye tono con ejemplos o adjetivos operativos; evita “profesional” sin concreción.
4) Formato: define estructura de salida (listas, campos, JSON) con validaciones.
5) Longitud: fija rango numérico (p.ej. 180–220 palabras) y qué hacer si se excede.
6) Calidad: criterios verificables (claridad, precisión, chequeos, fuentes) con señales de verificación.

Rúbrica (0–5 por eje):
5: Cumple totalmente y de forma operativa; incluye ejemplos/reglas/umbrales.
4: Cumple casi todo; una ambigüedad menor.
3: Aceptable pero con vacíos relevantes (p.ej. sin ejemplos ni rangos).
2: Parcial; vago o difícil de ejecutar.
1: Apenas presente; muy ambiguo.
0: Ausente o contradictorio.

Penalizaciones (aplica TODAS las que correspondan):
- Ambigüedad (“claro”, “formal”) sin definición operativa: −1
- Falta de rangos o umbrales numéricos cuando corresponden: −1
- Ortografía/gramática en el prompt: −1
- Falta de audiencia/usuario objetivo: −1
- Riesgo de incumplir requerimientos (formato, longitud) por falta de instrucciones: −1

Salida en JSON:
{
  "critique": "... sin cortesía, directo ...",
  "criteria": {"Rol": n, "Objetivo": n, "Tono": n, "Formato": n, "Longitud": n, "Calidad": n},
  "penalties": {"Ambiguedad": k, "SinUmbrales": k, "Ortografia": k, "SinAudiencia": k, "RiesgoFormato": k},
  "total_raw": sum(criteria),
  "total_final": total_raw - sum(penalizaciones),
  "max": 30
}
No redondees hacia arriba. Si dudas entre dos notas, elige la más BAJA.
"""

STRICT_CAP = True

def _safe_json_parse(txt: str):
    txt = (txt or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    if "{" in txt and "}" in txt:
        try:
            start = txt.index("{"); end = txt.rindex("}") + 1
            return json.loads(txt[start:end])
        except Exception:
            pass
    return {"critique": txt[:500], "criteria": {}, "penalties": {}}

def _postprocess_scorecard(sc: dict) -> dict:
    axes = ["Rol","Objetivo","Tono","Formato","Longitud","Calidad"]
    sc.setdefault("criteria", {})
    for a in axes:
        sc["criteria"][a] = int(max(0, min(5, sc["criteria"].get(a, 0))))
    total_raw = sum(sc["criteria"][a] for a in axes)
    sc.setdefault("penalties", {})
    pen_total = sum(int(v) for v in sc["penalties"].values() if isinstance(v, (int, float)))
    total_final = max(0, total_raw - int(pen_total))
    if STRICT_CAP and any(sc["criteria"][a] <= 2 for a in axes):
        total_final = min(total_final, 20)
    sc["total_raw"] = int(total_raw)
    sc["total_final"] = int(total_final)
    sc["max"] = 30
    return sc

def scorecard_gemini(prompt_to_score: str,
                     api_key: str | None = None,
                     model_name: str = "gemini-1.5-flash") -> dict:
    _configure_genai(api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=_SCORECARD_SYSTEM_STRICT,
    )
    user_msg = (
        "Evalúa el siguiente PROMPT según la rúbrica estricta y responde SOLO en JSON:\n\n"
        "=== PROMPT A EVALUAR ===\n"
        f"{prompt_to_score}\n"
        "=== FIN ==="
    )
    resp = model.generate_content(user_msg)
    raw_text = _extract_text_from_candidates(resp)
    sc = _safe_json_parse(raw_text)
    sc = _postprocess_scorecard(sc)
    sc["_mode"] = "gemini_strict"
    return sc

# ====== Normalizador para lo que espera el FRONT ======

def _sum_local_from_criteria(criteria_caps: dict):
    keys = ["Rol","Objetivo","Tono","Formato","Longitud","Calidad"]
    crit = criteria_caps or {}
    norm = {k: int(crit.get(k, crit.get(k.lower(), 0)) or 0) for k in keys}
    for k, v in norm.items():
        norm[k] = 0 if v < 0 else 5 if v > 5 else v
    return norm, sum(norm.values())

def _to_front_payload_v2(sc: dict, force_raw_total: bool = True) -> dict:
    norm_caps, suma_local = _sum_local_from_criteria(sc.get("criteria") or {})
    criteria_lower = {k.lower(): v for k, v in norm_caps.items()}
    chosen_total = suma_local  # usamos SIEMPRE la suma local
    return {
        "ok": True,
        "criteria": criteria_lower,
        "total": chosen_total,
        "score": chosen_total,
        "overall": chosen_total,
        "total_raw": chosen_total,
        "total_final": chosen_total,
        "max": 30,
        "scorecard": {
            "criteria": criteria_lower,
            "total": chosen_total,
            "total_raw": chosen_total,
            "total_final": chosen_total,
            "max": 30
        },
        "debug": {"sum_from_criteria": chosen_total}
    }

# === endpoint principal (sin caché) ===
@app.route("/api/scorecard", methods=["POST"])
@app.route("/scorecard", methods=["POST"])
def api_scorecard():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    model  = (data.get("model")  or "gemini-1.5-flash").strip()
    api_key= data.get("api_key")
    if not prompt:
        return jsonify({"ok": False, "error": "Falta 'prompt'."}), 400
    sc = scorecard_gemini(prompt, api_key=api_key, model_name=model)
    payload = _to_front_payload_v2(sc)  # <— usa v2
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp, 200


# =========================
#   5) Mejorar con IA online (opcional) — máx. 150 palabras
# =========================
@app.post("/improve-online")
@app.post("/api/improve-online")
def improve_online():
    if not _HAS_GENAI:
        return jsonify(error="Gemini no configurado. Define GEMINI_API_KEY."), 501

    data = request.get_json(silent=True) or {}
    base_prompt = (data.get("prompt", "") or "").strip()
    if not base_prompt:
        return jsonify(error="Falta 'prompt'."), 400

    # Pedimos explícitamente <=150 palabras y lo reforzamos con un recorte de seguridad
    llm = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_IMPROVER_MODEL", "gemini-1.5-flash"),
        system_instruction=(
            "Eres un mejorador de prompts. Reescribe el prompt para que sea claro, completo y accionable. "
            "Devuelve SOLO el prompt mejorado en un único bloque, sin comentarios extra, en **máximo 150 palabras**."
        ),
        generation_config={"temperature": 0.2, "max_output_tokens": 512},
    )

    resp = llm.generate_content(base_prompt)
    improved = _extract_text_from_candidates(resp) or (getattr(resp, "text", "") or "").strip()

    # Recorte de seguridad a 150 palabras
    words = improved.split()
    if len(words) > 150:
        improved = " ".join(words[:150])

    return jsonify(prompt=improved), 200

# =========================
#   6) Health y Home
# =========================
@app.get("/health")
@app.get("/api/health")
def health():
    routes = sorted([f"{r.methods} {r.rule}" for r in app.url_map.iter_rules()])
    return jsonify(ok=True, has_ollama=_HAS_OLLAMA, has_genai=_HAS_GENAI, routes=routes), 200

@app.get("/")
def home():
    try:
        return render_template("index.html")
    except Exception:
        return "GuíaIA API OK", 200


# ---------- DEBUG DE RUTAS (usar decorador clásico) ----------
from flask import jsonify
import inspect

@app.route("/__routes", methods=["GET"], strict_slashes=False)
def __routes():
    return jsonify(sorted([f"{r.rule} -> {','.join(sorted(r.methods))}"
                          for r in app.url_map.iter_rules()]))

@app.route("/scorecard/which", methods=["GET"], strict_slashes=False)
def which_scorecard_payload():
    func = globals().get("_to_front_payload_v2") or globals().get("_to_front_payload")
    return jsonify({
        "payload_func_used": func.__name__ if func else None,
        "signature": str(inspect.signature(func)) if func else None
    })


# =========================
#   Analytics: login + stats + query + events
# =========================

# Corrige el redirect del decorador a 'home' (no 'index')
def require_admin(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if session.get("admin_ok"):
            return view_func(*args, **kwargs)

        key = request.args.get("key") or request.headers.get("X-Admin-Key")
        if key == ADMIN_KEY:
            session["admin_ok"] = True
            session["fail_count"] = 0
            return view_func(*args, **kwargs)

        session["fail_count"] = session.get("fail_count", 0) + 1
        if session["fail_count"] >= 3:
            session.pop("fail_count", None)
            session.pop("admin_ok", None)
            return redirect(url_for("home"))  # <-- aquí: home

        accepts_html = "text/html" in (request.headers.get("Accept") or "")
        if accepts_html and request.method in ("GET", "HEAD"):
            return redirect(url_for("analytics_login"))
        return jsonify(ok=False, error="unauthorized"), 401
    return wrapper


@app.get("/analytics/login")
def analytics_login():
    html = """
    <!doctype html>
    <meta charset="utf-8">
    <title>Analytics Login</title>
    <style>
      body{font-family:system-ui,Arial;margin:40px}
      input{padding:8px 10px;font-size:16px}
      button{padding:8px 14px;font-size:16px;margin-left:8px}
      .msg{color:#b10000;margin-top:10px}
    </style>
    <h1>Analytics — Ingresar clave</h1>
    <form method="post" action="/analytics/login">
      <input type="password" name="key" placeholder="Admin key" autofocus>
      <button type="submit">Entrar</button>
    </form>
    {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
    """
    return render_template_string(html, msg=None)

@app.post("/analytics/login")
def analytics_login_post():
    key = (request.form.get("key") or "").strip()
    if key == ADMIN_KEY:
        session["admin_ok"] = True
        session["fail_count"] = 0
        return redirect(url_for("analytics_page"))
    session["fail_count"] = session.get("fail_count", 0) + 1
    if session["fail_count"] >= 3:
        session.pop("fail_count", None)
        session.pop("admin_ok", None)
        return redirect(url_for("home"))  # <-- aquí: home
    html = """
    <!doctype html>
    <meta charset="utf-8">
    <title>Analytics Login</title>
    <style>
      body{font-family:system-ui,Arial;margin:40px}
      input{padding:8px 10px;font-size:16px}
      button{padding:8px 14px;font-size:16px;margin-left:8px}
      .msg{color:#b10000;margin-top:10px}
    </style>
    <h1>Analytics — Ingresar clave</h1>
    <form method="post" action="/analytics/login">
      <input type="password" name="key" placeholder="Admin key" autofocus>
      <button type="submit">Entrar</button>
    </form>
    <div class="msg">Clave incorrecta. Intentos: {{ tries }}/3</div>
    """
    return render_template_string(html, tries=session["fail_count"])

@app.get("/analytics")
@require_admin
def analytics_page():
    return render_template("analytics.html")


# ---- STATS (única definición, protegida) ----
@app.get("/api/analytics/stats")
@require_admin
def analytics_stats():
    db = SessionLocal()
    try:
        total_sessions = db.execute(text("SELECT COUNT(*) FROM sessions")).scalar()

        row = db.execute(text("""
            SELECT 
              AVG(sm.time_on_page_ms)/1000.0 AS avg_seconds_on_page,
              AVG(NULLIF(sm.time_to_first_prompt_ms,0))/1000.0 AS avg_seconds_to_first,
              100.0 * SUM(CASE WHEN sm.improve_clicks_count>0 THEN 1 ELSE 0 END) / COUNT(*) AS pct_improved
            FROM session_metrics sm
        """)).mappings().first()

        top_countries = db.execute(text("""
            SELECT s.country, COUNT(*) AS n
            FROM sessions s
            GROUP BY s.country
            ORDER BY n DESC
            LIMIT 5
        """)).mappings().all()

        return jsonify(
            ok=True,
            total_sessions=total_sessions or 0,
            avg_seconds_on_page=(row or {}).get("avg_seconds_on_page"),
            avg_seconds_to_first=(row or {}).get("avg_seconds_to_first"),
            pct_improved=(row or {}).get("pct_improved"),
            top_countries=[dict(r) for r in (top_countries or [])]
        )
    finally:
        db.close()


# ---- QUERY (read-only) ----
@app.post("/api/analytics/query")
@require_admin
def analytics_query():
    payload = request.get_json(silent=True) or {}
    sql = (payload.get("sql") or "").strip()
    limit = int(payload.get("limit") or 100)
    limit = max(1, min(limit, 100))  # 1..100

    if not sql:
        return jsonify(ok=False, error="sql required"), 400

    upper = sql.upper().strip()

    # 1) Solo SELECT al inicio
    if not upper.startswith("SELECT"):
        return jsonify(ok=False, error="only SELECT is allowed"), 400

    # 2) Bloquea múltiples statements
    if ";" in sql:
        return jsonify(ok=False, error="multiple statements are not allowed"), 400

    # 3) Bloquea comandos peligrosos como PALABRAS COMPLETAS (no subcadenas)
    forbidden_words = r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REINDEX|VACUUM|PRAGMA|ATTACH|DETACH|COPY|GRANT|REVOKE)\b"
    if re.search(forbidden_words, upper):
        return jsonify(ok=False, error="keyword not allowed"), 400

    # 4) Si no trae LIMIT, lo añadimos (máx 100)
    if "LIMIT" not in upper:
        sql = f"{sql} LIMIT {limit}"

    db = SessionLocal()
    try:
        rs = db.execute(text(sql))
        rows = rs.fetchall()
        cols = rs.keys()
        out_rows = [{k: (None if v is None else str(v)) for k, v in zip(cols, r)} for r in rows]
        return jsonify(ok=True, columns=list(cols), rows=out_rows)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400
    finally:
        db.close()


# ---- EVENTOS ----
@app.post("/api/analytics/event")
def analytics_event():
    raw = request.get_data(cache=False, as_text=True)
    try:
        data = json.loads(raw) if raw else (request.get_json(force=True) or {})
    except Exception as e:
        print("DEBUG /api/analytics/event raw body:", raw)
        return jsonify(ok=False, error=f"bad json: {str(e)}"), 400

    device_id = (data.get("device_id") or "").strip()
    event = (data.get("event") or "").strip()
    payload = data.get("payload") or {}
    geo = data.get("geo") or {}
    ua = (data.get("user_agent") or request.headers.get("User-Agent") or "")[:250]
    ref = (data.get("referrer") or request.referrer or "")[:250]

    if not device_id or not event:
        return jsonify(ok=False, error="device_id y event son requeridos"), 400

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(device_id=device_id).one_or_none()
        if not user:
            user = User(device_id=device_id)
            db.add(user)
            db.flush()

        session_rec = (
            db.query(Session)
              .filter_by(user_id=user.id)
              .order_by(Session.started_at.desc())
              .first()
        )
        create_new_session = (event == "init_session") or (session_rec is None or session_rec.ended_at is not None)
        if create_new_session:
            geo_in = geo or {}
            if not geo_in.get("country"):
                geo_in = resolve_geo_from_request()

            session_rec = Session(
                user_id=user.id,
                ip_hash=None,
                country=geo_in.get("country"),
                city=geo_in.get("city"),
                user_agent=ua,
                referrer=ref,
            )
            db.add(session_rec)
            db.flush()
            db.add(SessionMetrics(session_id=session_rec.id))
        else:
            metrics = db.get(SessionMetrics, session_rec.id)
            if not metrics:
                metrics = SessionMetrics(session_id=session_rec.id)
                db.add(metrics)

        metrics = db.get(SessionMetrics, session_rec.id)

        if event == "end_session":
            session_rec.ended_at = func.now()

        elif event == "prompt_created":
            pjson = payload.get("prompt_initial_json") or {}
            if DATABASE_URL.startswith("postgresql"):
                db.add(Prompt(session_id=session_rec.id, prompt_initial_json=pjson))
            else:
                db.add(Prompt(session_id=session_rec.id, prompt_initial_json=json.dumps(pjson)))
            metrics.prompts_initial_count += 1
            ms_first = payload.get("time_to_first_prompt_ms")
            if isinstance(ms_first, int) and ms_first >= 0 and metrics.time_to_first_prompt_ms == 0:
                metrics.time_to_first_prompt_ms = ms_first

        elif event == "wrong_answer":
            metrics.wrong_answer_count += 1
        elif event == "improve_click":
            metrics.improve_clicks_count += 1
        elif event == "clipboard_copy":
            metrics.clipboard_copy_count += 1
        elif event == "new_prompt_click":
            metrics.new_prompt_clicks_count += 1
        elif event == "heartbeat":
            ms = payload.get("delta_ms")
            if isinstance(ms, int) and ms > 0:
                metrics.time_on_page_ms += ms

        db.commit()
        return jsonify(ok=True, session_id=str(session_rec.id)), 200

    except Exception as e:
        db.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        db.close()

@app.post("/analytics/logout")
def analytics_logout():
    # Limpia la sesión admin
    session.pop("admin_ok", None)
    session.pop("fail_count", None)
    return jsonify(ok=True)


# =========================
#   Main
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0")

    # Crear tablas si no existen (dev/primera vez)
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(bind=conn)
        print("DB ready ✅")
    except Exception as e:
        print("DB init error:", e)

    # Muestra rutas al arrancar (útil para verificar que /scorecard/which existe)
    print("== URL MAP al arrancar ==")
    for r in app.url_map.iter_rules():
      print(" ", r.rule, "->", ",".join(sorted(r.methods)))


    app.run(host=host, port=port, debug=os.getenv("FLASH_DEBUG", "false").lower() == "true")

