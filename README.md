# sharp-odds-gh — Pinnacle gratis vía GitHub Actions

Captura odds **sharp (Pinnacle)** de OddsPortal desde los runners de **GitHub Actions**
(IP de EE.UU.), donde OddsPortal sí muestra Pinnacle — cosa que la VM en México no puede
(la redirige a la versión MX sin Pinnacle). El runner scrapea y publica el JSON en el repo;
la VM de NFL/MLB lo consume gratis para el CLV / valor ML.

## Estado: v1 = DIAGNÓSTICO

OddsPortal le niega las odds a bots. Antes del extractor final, esta versión **confirma con
datos reales, desde un runner US**, si Pinnacle aparece y si la tabla de odds renderiza.
Publica `debug/<sport>_diag.json` + capturas (`debug/*.png`). Con eso se escribe el parser real.

## Setup (una vez)

1. Creá un repo nuevo en GitHub (público es más simple para que la VM lea el JSON crudo):
   por ej. `https://github.com/<tu-usuario>/sharp-odds-gh`.
2. Desde `D:\NFL\sharp-odds-gh` (ya está `git init` + commit hecho):
   ```bash
   git remote add origin https://github.com/<tu-usuario>/sharp-odds-gh.git
   git branch -M main
   git push -u origin main
   ```
3. En GitHub: pestaña **Actions** → habilitá los workflows → **Run workflow** (`scrape-sharp-odds`).
4. Cuando termine (~2-3 min), revisá `debug/mlb_diag.json` y las capturas (artifact
   "screenshots"). Ahí se ve si el runner US ve Pinnacle.

## Qué mira el diagnóstico

`debug/mlb_diag.json` reporta:
- `league_final_url`: ¿el runner cayó en la versión internacional (.com) o lo redirigió?
- `match_diag.mentions_pinnacle`, `books_in_text`, `book_img_alts`: qué casas aparecen.
- `price_count` + `price_sample`: si la tabla de odds renderiza y con qué estructura de DOM.

Si `mentions_pinnacle=true` y hay precios → seguimos al extractor real + consumo desde la VM.
Si el runner también recibe solo banners → pivotamos (API oficial de Pinnacle / consenso soft).

## Cadencia

El workflow corre cada 3h (cron) y a mano (workflow_dispatch). Se ajusta al validar el extractor.
