# GuíaIA — Documentación final de entrega (Módulo IV - DevOps)

**Autor:** José Marcelo Jara Vera  
**Proyecto:** GuíaIA — Chatbot paso a paso con validación, mejora con IA y consola de analítica  
**Repositorio base:** carpeta `GIUAIA-main`  

---

## 1) Título del proyecto

**GuíaIA: Chatbot educativo con IA generativa + analítica**  
Módulo IV — DevOps

---

## 2) Descripción general

GuíaIA es una aplicación web en Flask que guía al usuario a construir un prompt de calidad "paso a paso", valida coherencia con IA y ofrece una opción para **mejorar el prompt** con un modelo generativo (Gemini u Ollama). Además, instrumenta **eventos de uso** (inicio de sesión anónima, heartbeats, clics, tiempos) y provee una **consola de analítica** con login de administrador para consultas SQL de solo lectura.

**Características clave**
- Flujo guiado de preguntas y validación de coherencia.
- Mejora en línea del prompt con IA (Gemini u Ollama, con _fallback_).
- Registro de métricas por sesión (tiempo en página, clics, etc.).
- Consola de analítica protegida con clave admin (login) para visualizar KPIs y lanzar consultas SQL _read-only_.

---

## 3) Tecnologías utilizadas

- **Backend:** Python 3.11+, Flask 3, Flask-CORS, SQLAlchemy 2, python-dotenv.
- **Base de datos:** SQLite local (`dev.db`) y **PostgreSQL** para producción (Render). JSONB en Postgres; _string_ en SQLite.
- **IA generativa:** Google Gemini (paquete `google-generativeai`) y **Ollama** opcional (por defecto modelo `mistral`).
- **Frontend:** HTML5, CSS, JavaScript (vanilla). Plantillas Jinja (`templates/index.html`, `templates/analytics.html`).
- **Servidor de producción:** `gunicorn` (Render Web Service).
- **Recursos estáticos:** `/static/css`, `/static/js`, `/static/img`.

Archivo de dependencias: `requirements.txt`.

---

## 4) Instrucciones para ejecutar localmente

### 4.1. Prerrequisitos
- Python 3.11 o superior.
- (Opcional) Docker Desktop si deseas containerizar.
- (Opcional) Ollama local si quieres usar el provider alterno (`OLLAMA_HOST`).

### 4.2. Clonar e instalar
```bash
# 1) Ubícate en tu carpeta de trabajo y descomprime el proyecto
unzip GIUAIA-main.zip
cd GIUAIA-main

# 2) Crea y activa un entorno virtual
python -m venv venv
# Windows PowerShell
venv\Scripts\Activate.ps1
# macOS/Linux
# source venv/bin/activate

# 3) Instala dependencias
pip install -r requirements.txt
```

### 4.3. Variables de entorno (`.env`)
Crea un archivo `.env` en la raíz **sin comillas** alrededor de los valores:
```dotenv
# Claves de la app
SECRET_KEY=dev
ADMIN_KEY=Bootcamp1

# Base de datos (si NO se define, la app usa SQLite ./dev.db)
# Para Postgres (formato SQLAlchemy):
# postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
# DATABASE_URL=postgresql+psycopg://usuario:pass@host:5432/mi_db

# IA generativa (al menos uno de los dos)
GEMINI_API_KEY=tu_api_key
# O bien (alias compatible): GEMINI_APIKEY=tu_api_key
GEMINI_TEXT_MODEL=gemini-1.5-flash
GEMINI_VALIDATOR_MODEL=gemini-1.5-flash
GEMINI_IMPROVER_MODEL=gemini-1.5-flash

# Ollama (opcional)
OLLAMA_HOST=http://localhost:11434
LLM_MODEL=mistral

# Otros
HOST=0.0.0.0
PORT=5000
FLASH_DEBUG=false
GEO_TIMEOUT=2.0
BOOTCAMP_MODE=0
```

### 4.4. Inicializar BD y ejecutar
La app **autocreará** las tablas si no existen y usará `./dev.db` cuando no haya `DATABASE_URL`.
```bash
python app.py
# Visita: http://localhost:5000/
```

### 4.5. Acceso a la consola de analítica
- Ir a `http://localhost:5000/analytics` → pide **clave admin**.
- Clave por defecto (si no cambiaste `.env`): `Bootcamp1`.
- Endpoints relevantes:
  - `POST /analytics/login` (form-login)
  - `GET  /analytics` (resumen KPIs JSON, requiere sesión admin)
  - `POST /api/analytics/query` (SQL _read-only_)
  - `POST /api/analytics/event` (ingesta de eventos del frontend)
  - `POST /analytics/logout`

---

## 5) Proceso de despliegue (Render)

> Basado en la estructura del curso: frontend servido por Flask, backend en **Render Web Service** y **Base de datos PostgreSQL** en Render. 

1. **Crear servicio Postgres** en Render y obtener la cadena de conexión en formato SQLAlchemy:  
   `postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME`.
2. **Crear Web Service** en Render apuntando al repo/carpeta del proyecto.
3. **Build Command:** *(vacío; es Python)*  — Render instalará automáticamente vía `requirements.txt`.
4. **Start Command:** `gunicorn app:app`.
5. **Variables de entorno** en Render (Dashboard → Environment):
   - `SECRET_KEY` (valor robusto)
   - `ADMIN_KEY` (clave segura para la consola)
   - `DATABASE_URL` (cadena Postgres de tu servicio)
   - `GEMINI_API_KEY` (si usarás Gemini)
   - `GEMINI_TEXT_MODEL`, `GEMINI_VALIDATOR_MODEL`, `GEMINI_IMPROVER_MODEL` *(opcional)*
   - `FLASH_DEBUG=false`, `GEO_TIMEOUT=2.0`, `BOOTCAMP_MODE=0`
   - *(Opcional)* `OLLAMA_HOST`, `LLM_MODEL` si expones Ollama desde un host accesible para el servicio.
6. **Migración/Inicialización:** al iniciar, la app crea tablas si no existen.  
7. **URL pública:** Render asigna una URL del tipo `https://guiaia.onrender.com` (ejemplo). Añádela aquí cuando la tengas.

---

## 6) Desafíos y soluciones (aprendizajes)

- **Error “Failed to fetch” al mejorar prompt**  
  *Causa más común:* falta de `GEMINI_API_KEY` o CORS bloqueado.  
  *Solución:* definir `GEMINI_API_KEY` en `.env`/Render y verificar que el navegador no bloquee la petición; la app ya habilita CORS (`Flask-CORS`).

- **Variables con comillas en `.env`**  
  *Síntoma:* la aplicación lee comillas literales y falla la autenticación.  
  *Solución:* escribir `CLAVE=valor` **sin comillas** (p. ej. `GEMINI_API_KEY=abc123`).

- **Diferencia CRLF/LF en Git**  
  *Síntoma:* advertencias al hacer `git add` en Windows.  
  *Solución:* mantener por defecto; no afecta la ejecución. Alternativamente configurar `.gitattributes` si se desea uniformidad.

- **Botón/estilo de KPI**  
  Se removió el botón innecesario y se usó la paleta del sitio (clases CSS ya incluidas). El tablero carga KPIs automáticamente tras login.

---

## 7) Estructura del repositorio
```
GIUAIA-main/
├── app.py                # Aplicación Flask (rutas API, ORM, login admin, KPIs)
├── dev.db                # BD local SQLite (modo desarrollo)
├── requirements.txt      # Dependencias (Flask, SQLAlchemy, Gemini, gunicorn, etc.)
├── .env                  # (opcional/local) variables; NO subir con credenciales
├── templates/
│   ├── index.html        # Interfaz principal (flujo de preguntas)
│   └── analytics.html    # Consola de analítica (UI)
├── static/
│   ├── css/              # Estilos
│   ├── js/               # Lógica front (telemetría, validaciones, fetch)
│   └── img/              # Recursos gráficos
└── README.md             # Descripción breve
```

---

## 8) Modelo de datos y eventos

**Tablas (ORM SQLAlchemy):**
- `users`(id UUID pk, device_id único, created_at)
- `sessions`(id UUID pk, user_id fk→users.id, started_at, ended_at, ip_hash, country, city, user_agent, referrer)
- `session_metrics`(session_id pk/fk→sessions.id, prompts_initial_count, wrong_answer_count, improve_clicks_count, time_on_page_ms, time_to_first_prompt_ms, clipboard_copy_count, new_prompt_clicks_count)
- `prompts`(id UUID pk, session_id fk→sessions.id, prompt_initial_json JSONB/STRING, created_at)

**Eventos del frontend (ejemplos):** `init_session`, `heartbeat`, `copy`, `new_prompt_click`, `improve_click`, etc., enviados a `POST /api/analytics/event` con `device_id`, `event`, `payload`, `user_agent`, `referrer` y geo (si aplica).

---

## 9) Endpoints principales

- `GET  /` → interfaz principal (plantilla `index.html`).
- `POST /compose-initial` y `/api/compose-initial` → construcción inicial del prompt.
- `GET|POST /validate-step` y `/api/validate-step` → valida coherencia paso a paso.
- `POST /scorecard` y `/api/scorecard` → calcula/retorna _scorecard_.
- `POST /improve-online` y `/api/improve-online` → mejora el prompt con IA (Gemini/Ollama).
- `GET  /__routes` → lista de rutas expuestas.
- **Analítica (admin):**
  - `GET  /analytics` (resumen KPIs; requiere login admin)
  - `POST /analytics/login` (formulario)
  - `POST /analytics/logout`
  - `POST /api/analytics/query` (SQL _read-only_)
  - `POST /api/analytics/event` (ingesta de eventos)

> La consola de analítica (`templates/analytics.html`) consume los endpoints anteriores y muestra KPIs + cuadro de consultas SQL.

---

## 10) Consultas SQL útiles (KPIs)

- **Usuarios únicos que usaron “Mejorar con IA”**
```sql
SELECT COUNT(DISTINCT s.user_id) AS usuarios_mejoraron
FROM session_metrics sm
JOIN sessions s ON sm.session_id = s.id
WHERE sm.improve_clicks_count > 0;
```

- **% de sesiones con “Mejorar con IA”**
```sql
SELECT 100.0 * SUM(CASE WHEN improve_clicks_count > 0 THEN 1 ELSE 0 END) / COUNT(*) AS pct_mejoraron
FROM session_metrics;
```

- **Top 5 países por sesiones**
```sql
SELECT country, COUNT(*) AS n
FROM sessions
GROUP BY country
ORDER BY n DESC
LIMIT 5;
```

- **Tiempo promedio en página (segundos)**
```sql
SELECT AVG(time_on_page_ms) / 1000.0 AS avg_seconds_on_page
FROM session_metrics;
```

---

## 11) Seguridad y buenas prácticas

- **Protección de la consola:** cambia `ADMIN_KEY` por un valor seguro y no lo subas al repositorio.
- **CORS:** la app habilita CORS global; restringe orígenes en producción si lo necesitas.
- **REGEX anti-SQL malicioso:** el endpoint `/api/analytics/query` aplica reglas para evitar escritura/DDL; úsalo solo para lectura.
- **Secretos:** mantén `SECRET_KEY` y claves de IA en variables de entorno, nunca en Git.

---

## 12) URL de la app desplegada

- **Enlace público:** *(añadir aquí la URL una vez desplegada en Render)*  
- **Credenciales admin (solo para evaluación):** proporcionar temporalmente la clave al docente por canal seguro.

---

## 13) Créditos y licencia

- Íconos e imágenes: carpeta `static/img` (uso didáctico).  
- Código base y estructura: autor del proyecto.  
- Licencia: MIT (si aplica) o "Todos los derechos reservados" (elige y declara en el README).

---

### Anexo A — Comandos útiles
```bash
# Ejecutar en desarrollo
python app.py

# Probar endpoint de salud (si lo expones)
curl -i http://localhost:5000/__routes

# Enviar evento manual de prueba
curl -X POST http://localhost:5000/api/analytics/event \
  -H "Content-Type: application/json" \
  -d '{"device_id":"dev-123","event":"improve_click","payload":{}}'
```

### Anexo B — Checklist de entrega
- [x] Título + identificación del módulo
- [x] Descripción del proyecto (2–3 oraciones + bullets)
- [x] Tecnologías usadas (frontend/backend/BD/despliegue)
- [x] Instrucciones para ejecutar localmente (clonar, instalar, `.env`, run)
- [x] Proceso de despliegue (Render) y variables
- [x] Desafíos y soluciones
- [x] (Opcional) Estructura del repo, endpoints, SQL útiles
- [x] Enlace a la app desplegada (pendiente de completar tras publicar)
