@echo off
rem Marswalk: arranca la API en http://localhost:8000 (doble clic o "iniciar" en la terminal).
rem Si el repo del frontend (trinity-nasa-team/MarsWalk-web) esta clonado junto a este como ..\MarsWalk-web,
rem lo compila y lo sirve en el mismo puerto (FRONTEND_DIST). Si no, solo levanta la API.
rem Requiere .venv (y pnpm para la web), y .env con GROQ_API_KEY (no se sube a git).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [!] Falta .venv. Ejecuta: python -m venv .venv ^&^& .venv\Scripts\python -m pip install -e ".[dev]"
  pause & exit /b 1
)
if not exist ".env" echo [aviso] No hay .env: la IA del Habitat respondera "no configurada".

rem Libera el puerto 8000 si quedo un backend anterior.
rem (PowerShell: no depende del idioma de Windows, netstat dice LISTENING o ESCUCHANDO)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

set "WEB=%~dp0..\MarsWalk-web"
set "FRONTEND_DIST="
if exist "%WEB%\package.json" (
  echo === Compilando MarsWalk-web ===
  if not exist "%WEB%\node_modules" call pnpm --dir "%WEB%" install --frozen-lockfile
  call pnpm --dir "%WEB%" build || (echo [!] Fallo la compilacion de la web. & pause & exit /b 1)
  set "FRONTEND_DIST=%WEB%\dist"
  start "" http://localhost:8000
) else (
  echo [aviso] No se encontro ..\MarsWalk-web: solo arranca la API ^(docs en http://localhost:8000/api/docs^).
  start "" http://localhost:8000/api/docs
)

echo === Arrancando API en http://localhost:8000 (Ctrl+C para detener) ===
.venv\Scripts\python -m uvicorn marsmap.api.main:app --app-dir src --env-file .env --port 8000
