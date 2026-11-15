# 2026-11-14 — Separación en dos repos (frontend / backend)

## Qué se hizo
- **Frontend → repo nuevo `trinity-nasa-team/MarsWalk-web`** (privado). Contiene `marswalk/` en la raíz, con su
  historial (`git subtree split --prefix=marswalk`). También se migraron las ramas `fix/fase0-higiene` (→
  MarsWalk-web#1) y `fix/frontend-runtime` (→ MarsWalk-web#2).
- **Este repo (MarsWalk-v3) queda como backend**: API FastAPI, planificador, datos, specs, notebooks.
  - Se quitaron `marswalk/` y el visor legado `frontend/` (este último no se desplegaba; su historial sigue aquí).
  - `vercel.json`: solo el servicio `api` y el rewrite `/api/*`.
  - `CORS_ORIGINS` por defecto incluye `http://localhost:5174` (puerto de `pnpm dev` de la web).
  - `iniciar.bat`: arranca la API; si existe `../MarsWalk-web`, la compila y la sirve en :8000 como antes.
  - `CLAUDE.md` actualizado (comandos y estructura).
- Respaldo: etiqueta `pre-separacion-frontend` = `main` justo antes de separar.

## Frontend (MarsWalk-web)
- `VITE_API_URL` define la URL del backend (vacío → `/api`, proxy de Vite en dev).
- `vercel.json`, `.env.example`, CI (`pnpm test` + `pnpm build`), README y CLAUDE.md propios.

## Pendiente (manual, requiere acceso a Vercel)
1. Proyecto Vercel actual: queda solo como API al hacer merge de este PR.
2. Crear un proyecto Vercel nuevo importando `MarsWalk-web`; variable `VITE_API_URL=https://<backend>.vercel.app/api`.
3. En el proyecto del backend: `CORS_ORIGINS` con el dominio del frontend.
4. La rama de fase 0 quedó migrada a MarsWalk-web#1. La rama del arnés mezclaba backend (arnés) y frontend
   (`frontend/` CVE + transición del mapa en `marswalk/`): hay que rehacer su parte de frontend en MarsWalk-web.

## Decisiones
- D11 en `docs/decisiones.md`.
