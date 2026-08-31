"""
Scraper de odds SHARP (Pinnacle) desde OddsPortal, para correr en GitHub Actions.

Por qué GitHub Actions y no la VM: la VM está en México (OCI Querétaro) y OddsPortal la
redirige a la versión MX (cuotasahora), que NO lista Pinnacle. Los runners de GitHub
Actions corren desde IP de EE.UU. -> OddsPortal muestra la versión internacional CON
Pinnacle. El runner scrapea y publica el JSON; la VM solo lo consume (gratis).

MODO DIAGNÓSTICO (v1): OddsPortal le niega las odds a bots. Antes de construir el parser
final, este script CONFIRMA con datos reales, desde el runner US, si:
  1) la página internacional (con Pinnacle) carga,
  2) el navegador renderiza la tabla de odds (o solo banners),
  3) qué casas aparecen (¿está Pinnacle?).
Guarda debug/<sport>_diag.json + una captura. Con eso se escribe el extractor real.

Uso (en el runner):  python scraper.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DEBUG = ROOT / "debug"
DATA = ROOT / "data"
DEBUG.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

# páginas de liga (versión internacional .com; desde IP US no redirige a MX)
LEAGUES = {
    "mlb": "https://www.oddsportal.com/baseball/usa/mlb/",
    "nfl": "https://www.oddsportal.com/american-football/usa/nfl/",
}

# JS que corre EN la página: enumera casas y cuotas visibles (defensivo, sin selectores
# frágiles). Sirve para diagnosticar la estructura desde el primer run real.
EXTRACT_JS = r"""
() => {
  const body = document.body.innerText || "";
  const known = ['pinnacle','1xbet','bet365','marathonbet','williamhill','unibet',
    '888sport','bwin','betfair','betway','betboom','winpot','10bet','pointsbet',
    'draftkings','fanduel','caesars','betmgm','betcris','codere','betsson'];
  const foundText = known.filter(k => new RegExp(k, 'i').test(body));
  // logos/nombres de casa por img alt/title y enlaces a fichas
  const imgAlts = [...new Set(Array.from(document.querySelectorAll('img'))
      .map(i => (i.getAttribute('alt') || i.getAttribute('title') || '').trim())
      .filter(Boolean))];
  const bookImgs = imgAlts.filter(a => known.some(k => new RegExp(k, 'i').test(a)));
  // cuotas decimales visibles y el class de su contenedor (para armar el parser)
  const priceEls = Array.from(document.querySelectorAll('p,span,a,div'))
      .filter(e => /^\d{1,2}\.\d{2}$/.test((e.textContent || '').trim()));
  const prices = priceEls.slice(0, 12).map(e => ({
      txt: e.textContent.trim(),
      cls: (e.getAttribute('class') || '').slice(0, 60),
      pcls: (e.parentElement?.getAttribute('class') || '').slice(0, 60),
  }));
  // enlaces que identifican casa en la tabla
  const bmLinks = [...new Set(Array.from(document.querySelectorAll('a'))
      .map(a => a.getAttribute('href') || '')
      .filter(h => /bookmaker|\/out\/|betting-odds/i.test(h)))].slice(0, 20);
  return {
    body_len: body.length,
    mentions_pinnacle: /pinnacle/i.test(body),
    books_in_text: foundText,
    book_img_alts: bookImgs,
    all_img_alts: imgAlts.slice(0, 40),
    price_count: priceEls.length,
    price_sample: prices,
    bookmaker_links: bmLinks,
    title: document.title,
    url: location.href,
  };
}
"""


def diagnose(pw, sport: str, league_url: str) -> dict:
    browser = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
    ])
    ctx = browser.new_context(
        locale="en-US", timezone_id="America/New_York",
        viewport={"width": 1440, "height": 900},
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    )
    page = ctx.new_page()
    result: dict = {"sport": sport, "league_url": league_url,
                    "scraped_utc": datetime.now(timezone.utc).isoformat()}
    try:
        page.goto(league_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        result["league_title"] = page.title()
        result["league_final_url"] = page.url  # ¿redirigió a MX?
        # links a partidos de esta liga
        hrefs = page.eval_on_selector_all(
            "a[href]", "els => els.map(a => a.getAttribute('href'))")
        pat = "/baseball/" if sport == "mlb" else "/american-football/"
        matches = [h for h in hrefs if h and "/h2h/" in h and pat.split("/")[1] in h]
        matches = list(dict.fromkeys(matches))
        result["n_matches"] = len(matches)
        result["match_sample"] = matches[:5]
        # abrir un partido y diagnosticar su tabla de odds
        if matches:
            m = matches[0]
            murl = m if m.startswith("http") else "https://www.oddsportal.com" + m
            page.goto(murl, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)   # dar tiempo a decodificar/renderizar odds
            try:
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(3000)
            except Exception:
                pass
            result["match_url"] = murl
            result["match_diag"] = page.evaluate(EXTRACT_JS)
            page.screenshot(path=str(DEBUG / f"{sport}_match.png"), full_page=False)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        browser.close()
    return result


def main() -> None:
    sports = sys.argv[1:] or ["mlb", "nfl"]
    with sync_playwright() as pw:
        for sport in sports:
            if sport not in LEAGUES:
                continue
            print(f"[diag] {sport} ...", flush=True)
            res = diagnose(pw, sport, LEAGUES[sport])
            (DEBUG / f"{sport}_diag.json").write_text(
                json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
            md = res.get("match_diag", {})
            print(f"[diag] {sport}: matches={res.get('n_matches')} "
                  f"final_url={res.get('league_final_url')} "
                  f"pinnacle_in_text={md.get('mentions_pinnacle')} "
                  f"books={md.get('books_in_text')} prices={md.get('price_count')}",
                  flush=True)


if __name__ == "__main__":
    main()
