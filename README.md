# GuíaIA — Documentación final de entrega (Módulo IV - DevOps)

**Autor:** José Jara  
**Proyecto:** GuíaIA — Chatbot paso a paso con validación, mejora con IA y consola de analítica
**Repositorio base:** carpeta `GIUAIA-main` (https://github.com/marcelojara25/GUIAIA)  

---

## 1) Título del proyecto

**GuíaIA: Chatbot educativo con IA generativa + analítica**  
Módulo IV — DevOps

---

## 2) Descripción general

GuíaIA es una aplicación web en Flask que guía al usuario a construir un prompt de calidad "paso a paso", valida coherencia con IA y ofrece una opción para **mejorar el prompt** con el modelo generativo Gemini. Además, instrumenta **eventos de uso** (inicio de sesión anónima, heartbeats, clics, tiempos) y provee una **consola de analítica** con login de administrador para consultas SQL de solo lectura. El flujo de uso culmina cuando el usuario copia su prompt final al portapapeles para reutilizarlo fuera de la aplicación.

**Características clave**
- Flujo guiado de preguntas y validación de coherencia.
- Mejora en línea del prompt con IA (modelo Gemini).
- Registro de métricas por sesión (tiempo en página, clics, etc.).
- Consola de analítica protegida con clave admin (login) para visualizar KPIs y lanzar consultas SQL _read-only_.

---

## 3) Tecnologías utilizadas

- **Backend:** Python 3.11+, Flask 3, Flask-CORS, SQLAlchemy 2, python-dotenv.
- **Base de datos:** SQLite local (`dev.db`) y **PostgreSQL** para producción (Render). JSONB en Postgres; _string_ en SQLite.
- **IA generativa:** Google Gemini (paquete `google-generativeai`).  
- **Frontend:** HTML5, CSS, JavaScript (vanilla). Plantillas Jinja (`templates/index.html`, `templates/analytics.html`).
- **Servidor de producción:** `gunicorn` (Render Web Service).
- **Recursos estáticos:** `/static/css`, `/static/js`, `/static/img`.

Archivo de dependencias: `requirements.txt`.

---

## 4) Instrucciones para ejecutar localmente

## 4.1. Prerrequisitos
- Python 3.11 o superior instalado.
- Git instalado para clonar el repositorio.

## 4.2. Clonar e instalar

```bash
# 1) Clona el repositorio
git clone https://github.com/marcelojara25/GUIAIA.git
cd GUIAIA

# 2) Crea y activa un entorno virtual
python -m venv venv
# Windows PowerShell
venv\Scripts\Activate.ps1
# macOS/Linux
source venv/bin/activate

# 3) Instala dependencias
pip install -r requirements.txt
```

## 4.3. Variables de entorno (`.env`)
Crea un archivo `.env` en la raíz **sin comillas** alrededor de los valores:
```dotenv
# Claves de la app
SECRET_KEY=dev
ADMIN_KEY=Bootcamp1

# Base de datos (si no defines, la app usa SQLite ./dev.db por defecto)
# DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME

# Clave para IA generativa
GEMINI_API_KEY=tu_api_key
GEMINI_TEXT_MODEL=gemini-1.5-flash
GEMINI_VALIDATOR_MODEL=gemini-1.5-flash
GEMINI_IMPROVER_MODEL=gemini-1.5-flash

# Configuración del servidor
HOST=0.0.0.0
PORT=5000
```

## 4.4. Inicializar BD y ejecutar
La app **autocreará** las tablas si no existen y usará `./dev.db` cuando no haya `DATABASE_URL`.
```bash
python app.py
# Abrir en navegador: http://localhost:5000/
```

## 4.5. Acceso a la consola de analítica
- Ir a `http://localhost:5000/analytics` → pide **clave admin**.
- Clave por defecto (si no cambiaste `.env`): `Bootcamp1`.
- Endpoints relevantes:
  - `POST /analytics/login` (form-login)
  - `GET  /analytics` (resumen KPIs JSON, requiere sesión admin)
  - `POST /api/analytics/query` (SQL _read-only_)
  - `POST /api/analytics/event` (ingesta de eventos del frontend)
  - `POST /analytics/logout`

Nota: aunque la app detecta si Ollama está instalado, actualmente todo el flujo de IA se ejecuta con Gemini.

---

## 5) Proceso de despliegue (Render)

El proyecto está desplegado en [Render](https://render.com), sirviendo el frontend con Flask y el backend como **Web Service** de Python. La base de datos es **PostgreSQL** en Render.

- **URL pública:**  
  - Aplicación: [https://guiaia.onrender.com/](https://guiaia.onrender.com/)  
  - Consola de analítica (requiere clave admin): [https://guiaia.onrender.com/analytics](https://guiaia.onrender.com/analytics)  

### 5.1. Base de datos
- Crear un servicio **PostgreSQL** en Render.  
- Obtener la cadena de conexión en formato SQLAlchemy:  
`postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME`
- Asignarla a la variable de entorno `DATABASE_URL`.
- ✅ La app ejecuta `Base.metadata.create_all(...)` al arrancar, por lo que las tablas se crean automáticamente si no existen.

### 5.2. Web Service en Render
- Crear un nuevo **Web Service** apuntando al repositorio GitHub del proyecto.  
- **Build Command:** *(vacío; es Python)*  — Render instalará automáticamente vía `requirements.txt`.
- **Start Command:** `gunicorn app:app`.

> Basado en la estructura del curso: frontend servido por Flask, backend en **Render Web Service** y **Base de datos PostgreSQL** en Render.

### 5.3. Variables de entorno

En el Dashboard de Render → *Environment*, se configuraron las siguientes variables (ejemplo real de este despliegue):

- `SECRET_KEY=dev`
- `ADMIN_KEY=Bootcamp1`
- `DATABASE_URL=postgresql+psycopg://...`
- `GEMINI_API_KEY=********`
- `DEBUG=False`
- `PYTHON_VERSION=3.11.9`
- `PIP_ONLY_BINARY=:all:`

### 5.4. Migración / Inicialización

- No se requieren pasos manuales de migración.  
- Al iniciar, la app crea las tablas automáticamente en la base de datos configurada (`Postgres` en Render o `SQLite` local).

---

## 6) Desafíos y soluciones (aprendizajes)

- **Compatibilidad con versiones de Python en Render:**  
  Inicialmente Render intentaba ejecutar la app con **Python 3.13**, lo cual generaba fallos de arranque.  
  La solución fue declarar explícitamente la versión soportada (`PYTHON_VERSION=3.11.9`) en las variables de entorno de Render, lo que permitió estabilizar el despliegue.

- **Depuración y soporte con IA:**  
  Durante el desarrollo se presentaron múltiples errores de sintaxis y dependencias en la consola.  
  El uso de herramientas de **IA generativa** permitió identificar y resolver los errores más rápido, reduciendo el tiempo de prueba y error en la depuración.

- **Complejidad del código en Python:**  
  Para cumplir con todas las funcionalidades (registro de sesiones, validaciones paso a paso, scorecard, consola de analítica), fue necesario escribir un volumen significativo de código en Python.  
  Aunque el resultado final es funcional, **no se alcanzó a optimizar el código por motivos de tiempo**, lo que queda como área de mejora para futuras versiones.

- **Aprendizajes clave:**  
  - Importancia de planificar la **gestión de dependencias** y versiones desde el inicio para evitar bloqueos en despliegue.  
  - Valor de la **integración temprana con una base de datos real (Postgres en Render)** para asegurar persistencia y analítica.  
  - La IA puede ser un **aliado práctico en depuración y validación**, acelerando el ciclo de desarrollo.  
  - La experiencia demostró la necesidad de **equilibrar alcance vs. optimización** en proyectos con plazos limitados.

---

## 7) Estructura del repositorio
```
GIUAIA-main/
├── app.py                # Aplicación Flask (rutas API, ORM, login admin, KPIs)
├── dev.db                # BD local SQLite (modo desarrollo)
├── requirements.txt      # Dependencias (Flask, SQLAlchemy, Gemini, gunicorn, etc.)
├── .env                  # (opcional/local) Variables; NO subir con credenciales
├── templates/            # Plantillas Jinja (interfaz web)
│   ├── index.html        # Interfaz principal (flujo de preguntas)
│   └── analytics.html    # Consola de analítica (UI)
├── static/               # Archivos estáticos
│   ├── css/              # Estilos
│   ├── js/               # Lógica front (telemetría, validaciones, fetch)
│   └── img/              # Recursos gráficos
└── README.md             # Documentacion del proyecto
```

---

## 8) Modelo de datos y eventos

El sistema utiliza **SQLAlchemy** para definir las tablas tanto en **SQLite** (modo local) como en **PostgreSQL** (producción).  
Las tablas se crean automáticamente al iniciar la aplicación si no existen.

### 8.1. Tablas principales

- **users**  
  - `id` (UUID, PK)  
  - `device_id` (string único – identifica un dispositivo/usuario anónimo)  
  - `created_at` (fecha de registro)

- **sessions**  
  - `id` (UUID, PK)  
  - `user_id` (FK → users.id)  
  - `started_at`, `ended_at`  
  - `ip_hash`, `country`, `city`, `user_agent`, `referrer`

- **session_metrics**  
  - `session_id` (UUID, PK, FK → sessions.id)  
  - `prompts_initial_count`  
  - `wrong_answer_count`  
  - `improve_clicks_count`  
  - `time_on_page_ms`  
  - `time_to_first_prompt_ms`  
  - `clipboard_copy_count`  
  - `new_prompt_clicks_count`

- **prompts**  
  - `id` (UUID, PK)  
  - `session_id` (FK → sessions.id)  
  - `prompt_initial_json` (JSONB en Postgres / string en SQLite)  
  - `created_at`

### 8.2. Eventos registrados

El frontend envía eventos a `POST /api/analytics/event`, que se guardan en las tablas anteriores:

- `init_session` → inicia una nueva sesión.  
- `end_session` → marca fin de sesión.  
- `prompt_created` → almacena un prompt inicial (JSON).  
- `wrong_answer` → incrementa contador de respuestas inválidas.  
- `improve_click` → usuario pidió mejora con IA.  
- `clipboard_copy` → usuario copió el prompt al portapapeles.  
- `new_prompt_click` → usuario generó un nuevo prompt.  
- `heartbeat` → mide tiempo activo en página (`time_on_page_ms`).

El flujo típico del usuario concluye cuando utiliza el evento `clipboard_copy`, es decir, al copiar su prompt mejorado desde la aplicación hacia su portapapeles para usarlo externamente.

### 8.3. Uso en analítica

Estos datos alimentan la **consola de analítica**, donde se pueden consultar:
- Número total de sesiones.  
- Promedio de tiempo en página.  
- Tiempo promedio al primer prompt.  
- % de usuarios que usaron la mejora con IA.  
- Países con más sesiones.
---

## 9) Endpoints principales

### 9.1. Flujo de prompts
- `GET /questions` — Devuelve las preguntas iniciales para construir el prompt.  
- `POST /validate-step` — Valida la coherencia de una respuesta (con reglas + Gemini).  
- `POST /compose-initial` — Genera el prompt inicial a partir de las respuestas.  
- `POST /scorecard` — Evalúa el prompt con una rúbrica estricta (Gemini).  
- `POST /improve-online` — Devuelve una versión mejorada del prompt (máx. 150 palabras).

### 9.2. Analítica (requiere clave admin)
- `GET /analytics/login` — Página para ingresar clave admin.  
- `POST /analytics/login` — Valida la clave admin.  
- `GET /analytics` — UI de la consola de analítica.  
- `GET /api/analytics/stats` — Estadísticas globales (sesiones, tiempos, % de mejora, países top).  
- `POST /api/analytics/query` — Ejecuta consultas SQL _read-only_.  
- `POST /api/analytics/event` — Registra un evento del frontend.  
- `POST /analytics/logout` — Cierra sesión admin.

### 9.3. Utilitarios
- `GET /health` — Devuelve estado del servicio (disponibilidad, proveedores IA activos).  
- `GET /__routes` — Lista todas las rutas expuestas (modo debug).  
- `GET /scorecard/which` — Indica qué payload usa la API de scorecard (debug).

---

📌 **Nota:** La consola de analítica (`templates/analytics.html`) consume estos endpoints para mostrar KPIs interactivos y ofrecer un cuadro de consultas SQL con permisos de solo lectura.

---

## 10) Consultas SQL útiles (KPIs)

- **Usuarios únicos que usaron “Mejorar con IA”**
```sql
SELECT COUNT(DISTINCT s.user_id) AS usuarios_mejoraron
FROM session_metrics sm
JOIN sessions s ON sm.session_id = s.id
WHERE sm.improve_clicks_count > 0
```

- **% de sesiones con “Mejorar con IA”**
```sql
SELECT 100.0 * SUM(CASE WHEN improve_clicks_count > 0 THEN 1 ELSE 0 END)::float / COUNT(*) AS pct_mejoraron
FROM session_metrics
```

- **Top 5 países por sesiones**
```sql
SELECT country, COUNT(*) AS n
FROM sessions
GROUP BY country
ORDER BY n DESC
LIMIT 5
```

- **Tiempo promedio en página (segundos)**
```sql
SELECT AVG(time_on_page_ms) / 1000.0 AS avg_seconds_on_page
FROM session_metrics
```

- **Tiempo promedio hasta el primer prompt (segundos)**
```sql
SELECT AVG(NULLIF(time_to_first_prompt_ms,0)) / 1000.0 AS avg_seconds_to_first
FROM session_metrics
```

---

## 11) Seguridad y buenas prácticas

- **Protección de la consola (admin):** usa `ADMIN_KEY` como **secreto en entorno** (Render → Environment). Cámbiala por una fuerte (no “Bootcamp1”) y **no** la subas a Git. La sesión admin se mantiene por cookie; tras 3 intentos fallidos redirige al home.
- **CORS:** por simplicidad está habilitado globalmente para desarrollo. En producción **restringe orígenes** a tu dominio (`https://guiaia.onrender.com`) para reducir exposición.
- **SQL _read-only_ en consola:** el endpoint `/api/analytics/query`:
  - Acepta **solo `SELECT`** al inicio.
  - **Bloquea** múltiples sentencias (`;`) y palabras DDL/WRITE (p. ej., `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, etc.).
  - **Auto-LIMIT** a 100 filas si no se especifica.
- **Gestión de secretos:** mantén `SECRET_KEY`, `ADMIN_KEY` y `GEMINI_API_KEY` **solo en variables de entorno**. Nunca en el repositorio.
- **DEBUG y logs:** en Render, deja `DEBUG=False`. Evita volcar trazas o datos sensibles en logs.
- **Datos mínimos y privacidad:** se registra un `device_id` anónimo y métricas de sesión. No recolecta PII. Geo se resuelve vía API pública con _timeout_ bajo; si falla, queda `None`.
- **Dependencias y runtime:** versión explícita `PYTHON_VERSION=3.11.9` (evita fallos con 3.13). Dependencias en `requirements.txt` y `PIP_ONLY_BINARY=:all:` para builds más estables.
- **Hardening sugerido (pendiente/futuro):**
  - Restringir CORS por lista blanca.
  - Cookies de sesión con `Secure`, `HttpOnly`, `SameSite=Lax` (según políticas de tu plataforma).
  - Rate-limit para `/api/analytics/event` si esperas alto tráfico.
  - Tests automáticos para el guard de SQL.

---

## 12) URL de la app desplegada

- **Enlace público:**  
  - App: https://guiaia.onrender.com/  
  - Consola de analítica: https://guiaia.onrender.com/analytics  *(requiere clave admin)*
