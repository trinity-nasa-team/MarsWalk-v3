# 2026-11-15 — Asistente de voz del HUD (tipo «Cortana») con Groq

## Qué se hizo
- `src/marsmap/api/routers/assistant.py`:
  - `POST /api/assistant/text` `{message, history}` y `POST /api/assistant/voice` `{audio_b64, mime, history}`.
  - Voz: Groq **Whisper `whisper-large-v3`** en `audio/translations` → transcribe en cualquier idioma y devuelve
    **inglés** (el usuario habla español o inglés sin elegir).
  - Interpretación: LLM de Groq (`GROQ_MODEL`, por defecto `openai/gpt-oss-120b`) en modo JSON →
    `{heard_en, kind: move|answer, robot_cmd, reply_en}`, validado con Pydantic. `robot_cmd` solo puede ser
    `forward|backward|left|right|stop`; cualquier otra cosa → respuesta (nunca mueve).
  - Candado: autorizar/aprobar la ruta nunca es una orden de movimiento (prompt + regex en código).
  - El backend NO mueve el robot: devuelve la orden y la web la manda a la Raspberry (mismo túnel de la cámara).
  - Sin dependencias nuevas: audio en base64 (máx. ~1.5 MB) y multipart a Groq con la librería estándar.
  - Mismo límite de mensajes que el chat del hábitat (`CHAT_RATE_LIMIT_PER_MINUTE`) y errores `ErrorOut`.
- `main.py`: registra el router y deja `app.state.llm_json` / `app.state.llm_transcribe` sustituibles en pruebas.
- `tests/api/test_assistant.py`: 10 pruebas con Groq fingido (sin red).

## Probado con Groq real (local)
«muévete un poquito hacia la izquierda» → left · «echa para atrás» → backward · «dale para adelante» → forward ·
«no te muevas» → stop · «¿cuántas lunas tiene Marte?» → respuesta · «autoriza la ruta» → sin movimiento.

## Configuración
- `GROQ_API_KEY` en el `.env` local (no se sube) y en Vercel (`marswalk-v3`, Secret).
- En local el puerto 8000 estaba ocupado; se usó `--port 8001` y la web con `API_PROXY_TARGET=http://127.0.0.1:8001`.

## Pendiente
- Rotar la clave de Groq (se compartió en el chat de trabajo).
