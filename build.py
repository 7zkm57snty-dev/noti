import json
import re
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).parent
SITE = BASE / "site"
NOTAS = SITE / "notas"
CACHE = BASE / "cache.json"

SECCIONES = [
    "Cali", "Valle del Cauca", "Colombia", "Internacional",
    "Deportes", "Tecnología", "Economía", "Tendencias", "Humor y opinión"
]
COLOMBIA_TZ = timezone(timedelta(hours=-5))
SECCIONES_DISPONIBLES = []


def escapar(valor):
    return html.escape(str(valor or ""), quote=True)


def cargar_json(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return defecto


def slug(texto):
    texto = str(texto or "").lower()
    for original, nuevo in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        texto = texto.replace(original, nuevo)
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:75]


def fecha_actual():
    return datetime.now(COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p")


def imagen_segura(url):
    url = str(url or "").strip()
    return escapar(url) if url.startswith(("https://", "http://")) else ""


def etiqueta_estado(noticia):
    estado = str(noticia.get("estado_informacion", "")).strip().lower()
    if not estado and "varias fuentes independientes" in str(noticia.get("verificacion", "")).lower():
        estado = "confirmada"
    etiquetas = {
        "confirmada": ("Confirmada", "confirmada"),
        "en_desarrollo": ("En desarrollo", "desarrollo"),
        "informacion_preliminar": ("Información preliminar", "preliminar")
    }
    texto, clase = etiquetas.get(estado, ("Actualidad", "actualidad"))
    return f'<span class="estado-noticia estado-{clase}" aria-label="Estado de la información: {texto}">{texto}</span>'


CSS = """
:root {
  --paper: #f5f4f0;
  --surface: #ffffff;
  --ink: #181818;
  --muted: #656565;
  --line: #dedbd4;
  --red: #b32931;
  --dark: #17191d;
  --width: 1260px;
  --serif: Georgia, "Times New Roman", serif;
  --sans: Arial, Helvetica, sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 18px; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans); }
a { color: inherit; text-decoration: none; }
img { display: block; max-width: 100%; }
button, input { font: inherit; }
[hidden] { display: none !important; }

.topline { background: var(--dark); color: #f8f6f1; }
.topline-inner {
  max-width: var(--width); margin: auto; min-height: 30px; padding: 6px 24px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
}
.topline strong { color: #f06a70; letter-spacing: 1.6px; }
.masthead { background: var(--surface); border-bottom: 1px solid var(--line); }
.brand-row {
  max-width: var(--width); margin: auto; padding: 22px 24px 18px;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
}
.brand-name {
  font-family: var(--serif); font-size: clamp(43px, 5.4vw, 70px);
  font-weight: 800; letter-spacing: -3.8px; line-height: .9;
}
.brand-name span { color: var(--red); }
.brand-tagline { margin-top: 9px; color: var(--muted); font-size: 10px; letter-spacing: 2.4px; text-transform: uppercase; }
.brand-social { display: flex; align-items: center; gap: 9px; font-size: 11px; }
.brand-social svg { width: 26px; height: 26px; color: var(--red); flex: none; }
.brand-social span { display: flex; flex-direction: column; gap: 3px; }
.brand-social small { color: var(--muted); font-size: 10px; }
.edition { text-align: right; color: var(--muted); font-size: 10px; line-height: 1.7; text-transform: uppercase; letter-spacing: .7px; }

.primary-nav { background: var(--surface); border-top: 1px solid var(--line); border-bottom: 1px solid var(--ink); }
.nav-inner {
  max-width: var(--width); margin: auto; padding: 0 24px;
  display: flex; align-items: center; gap: 0; overflow-x: auto;
  scrollbar-width: none; white-space: nowrap; -webkit-overflow-scrolling: touch;
}
.nav-inner::-webkit-scrollbar { display: none; }
.nav-inner a {
  display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px;
  border-right: 1px solid #ece9e3; font-size: 10px; font-weight: 800;
  letter-spacing: .7px; text-transform: uppercase; flex: 0 0 auto;
}
.nav-inner a:first-child { padding-left: 0; }
.nav-inner a:hover, .nav-inner a:focus-visible { color: var(--red); }
.nav-inner .nav-page { color: var(--red); }

.toolbar {
  max-width: var(--width); margin: auto; padding: 11px 24px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.search { display: flex; align-items: center; gap: 8px; width: min(460px, 100%); }
.search input {
  width: 100%; min-width: 0; padding: 10px 12px; background: var(--surface);
  border: 1px solid var(--line); border-radius: 2px; font-size: 12px; color: var(--ink);
}
.mode-button {
  padding: 9px 12px; color: var(--ink); background: transparent;
  border: 1px solid var(--ink); border-radius: 2px; cursor: pointer;
  font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px;
}
.mode-button:hover { background: var(--ink); color: #fff; }

.page { max-width: var(--width); margin: auto; padding: 0 24px 50px; }
.section-kicker {
  display: flex; align-items: center; gap: 12px; margin: 23px 0 15px;
  color: var(--red); font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase;
}
.section-kicker::after { content: ""; height: 1px; flex: 1; background: var(--line); }
.lead-layout {
  display: grid; grid-template-columns: minmax(0, 1.85fr) minmax(270px, .85fr);
  gap: 22px; align-items: stretch;
}
.lead-story {
  min-width: 0; background: var(--surface); border: 1px solid var(--line);
  display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(280px, .88fr);
}
.lead-image {
  min-width: 0; align-self: stretch; background: #e9e6df;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.lead-image img { width: 100%; height: 100%; object-fit: contain; object-position: center; }
.lead-copy { min-width: 0; padding: 27px 25px; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; }
.category-label { color: var(--red); font-size: 10px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; }
.state-wrap { margin-top: 7px; }
.state-badge {
  display: inline-flex; align-items: center; gap: 6px; margin: 0;
  padding: 5px 8px; border-radius: 2px; font-size: 9px; font-weight: 800;
  letter-spacing: .55px; text-transform: uppercase;
}
.state-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.state-actualidad { color: #40515e; background: #edf0f2; }
.state-confirmada { color: #23613b; background: #e5f2e9; }
.state-desarrollo { color: #805d1d; background: #f7eedb; }
.state-preliminar { color: #9b3438; background: #f6e4e3; }
.lead-copy h1 {
  margin: 11px 0 12px; font-family: var(--serif);
  font-size: clamp(29px, 3.1vw, 43px); line-height: 1.06; letter-spacing: -.8px;
}
.lead-copy p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.7; }
.story-meta { margin-top: 14px; color: #888; font-size: 9px; text-transform: uppercase; letter-spacing: .8px; }
.read-link {
  display: inline-flex; align-items: center; gap: 11px; margin-top: 18px;
  padding: 10px 0; border-top: 1px solid var(--ink); border-bottom: 1px solid var(--ink);
  font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .7px;
}
.read-link:hover { color: var(--red); border-color: var(--red); }

.explore-panel {
  min-width: 0; padding: 20px; background: #fff; border: 1px solid var(--line);
  border-top: 3px solid var(--red); display: flex; flex-direction: column; gap: 13px;
}
.panel-overline { color: var(--red); font-size: 9px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; }
.explore-panel h2 { margin: 0; font-family: var(--serif); font-size: 25px; line-height: 1.08; }
.explore-panel > p { margin: -5px 0 0; color: var(--muted); font-size: 11px; line-height: 1.5; }
.section-links { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.section-chip {
  min-width: 0; min-height: 38px; display: flex; align-items: center; justify-content: space-between;
  gap: 6px; padding: 8px 9px; border: 1px solid #e7e3dc; background: #f7f5f0;
  font-size: 10px; font-weight: 700;
}
.section-chip small { color: #777; font-size: 9px; }
.section-chip:hover { color: var(--red); border-color: var(--red); }
.panel-links { margin-top: auto; display: grid; gap: 0; border-top: 1px solid var(--line); }
.panel-links a { padding: 11px 0 0; font-size: 10px; font-weight: 800; letter-spacing: .4px; text-transform: uppercase; }
.panel-links a:hover { color: var(--red); }

.category-block { margin-top: 33px; padding-top: 22px; border-top: 1px solid var(--ink); scroll-margin-top: 12px; }
.category-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 15px; }
.category-heading h2 { margin: 0; font-family: var(--serif); font-size: clamp(25px, 3vw, 34px); letter-spacing: -.45px; }
.category-heading a { color: var(--red); font-size: 9px; font-weight: 800; letter-spacing: .7px; text-transform: uppercase; white-space: nowrap; }
.news-track {
  display: flex; align-items: stretch; gap: 18px; width: 100%; overflow-x: auto; overflow-y: hidden;
  padding: 0 0 12px; scrollbar-width: none; scroll-behavior: auto; overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch;
}
.news-track::-webkit-scrollbar { display: none; }
.story-card {
  flex: 0 0 clamp(340px, 35vw, 440px); min-width: 0; overflow: hidden;
  display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--line);
}
.story-link { display: flex; flex-direction: column; height: 100%; }
.story-image {
  width: 100%; aspect-ratio: 16 / 9; background: #e9e6df;
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.story-image img { width: 100%; height: 100%; object-fit: contain; object-position: center; }
.story-copy { padding: 13px 15px 16px; display: flex; flex: 1; flex-direction: column; align-items: flex-start; }
.story-copy h3 { margin: 8px 0 7px; font-family: var(--serif); font-size: 21px; line-height: 1.16; }
.story-copy p {
  margin: 0 0 13px; color: var(--muted); font-size: 11px; line-height: 1.6;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden;
}
.story-copy .read-more { margin-top: auto; color: var(--red); font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .7px; }
.story-card:hover .story-copy h3 { color: var(--red); }
.track-controls { display: flex; justify-content: flex-end; gap: 7px; margin-top: 4px; }
.track-controls button {
  width: 30px; height: 28px; border: 1px solid var(--line); background: var(--surface);
  color: var(--ink); cursor: pointer;
}
.track-controls button:hover { border-color: var(--red); color: var(--red); }

.article-page { max-width: 900px; margin: 35px auto 65px; padding: 0 24px; }
.article-header { max-width: 780px; margin: 0 auto 24px; }
.back-link { display: inline-block; margin-bottom: 24px; color: var(--red); font-size: 10px; font-weight: 800; letter-spacing: .8px; text-transform: uppercase; }
.article-page h1 { margin: 12px 0 14px; font-family: var(--serif); font-size: clamp(36px, 5.5vw, 62px); line-height: 1.04; letter-spacing: -1px; }
.article-summary { margin: 0; color: var(--muted); font-size: clamp(16px, 2vw, 20px); line-height: 1.6; }
.article-meta { margin-top: 18px; color: #888; font-size: 10px; letter-spacing: .7px; text-transform: uppercase; }
.preliminary-note { margin-top: 14px; padding: 12px 14px; border-left: 3px solid #b88732; background: #f2eadb; color: #55472f; font-size: 12px; line-height: 1.6; }
.article-figure { margin: 24px auto; background: #e9e6df; display: flex; justify-content: center; align-items: center; }
.article-figure img { width: 100%; height: auto; max-height: 72vh; object-fit: contain; }
.image-credit { margin: -14px auto 26px; max-width: 760px; color: #777; font-size: 10px; line-height: 1.5; }
.article-body { max-width: 760px; margin: auto; color: #292929; font: 18px/1.85 Georgia, serif; white-space: pre-line; }
.article-body p { margin: 0 0 23px; }
.sources { max-width: 760px; margin: 38px auto 0; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
.sources strong { color: var(--ink); font-size: 10px; letter-spacing: .8px; text-transform: uppercase; }
.sources li { margin: 7px 0; }
.related { max-width: 760px; margin: 44px auto 0; }
.related h2 { font-family: var(--serif); font-size: 26px; }
.related-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.related-grid .story-card { flex: initial; }

.editorial-page { max-width: 1040px; margin: auto; padding: 45px 24px 65px; }
.eyebrow { color: var(--red); font-size: 10px; font-weight: 800; letter-spacing: 1.7px; text-transform: uppercase; }
.editorial-page h1 { margin: 12px 0 15px; font: 800 clamp(38px, 5.7vw, 62px)/1.03 var(--serif); letter-spacing: -1px; }
.editorial-intro { max-width: 780px; margin: 0 0 30px; color: var(--muted); font-size: 17px; line-height: 1.7; }
.info-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.info-card { padding: 21px; background: var(--surface); border: 1px solid var(--line); }
.info-card h2 { margin: 0 0 10px; font: 700 22px var(--serif); }
.info-card p, .info-card li { color: var(--muted); font-size: 12px; line-height: 1.75; }
.info-card ul { padding-left: 18px; }
.newsletter-list { max-width: 900px; border-top: 1px solid var(--line); }
.newsletter-item { display: grid; grid-template-columns: 130px 1fr; gap: 18px; padding: 17px 0; border-bottom: 1px solid var(--line); }
.newsletter-item time { color: #888; font-size: 10px; }
.newsletter-item h2 { margin: 7px 0; font: 700 22px/1.2 var(--serif); }
.newsletter-item p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.site-map-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.site-map-list { list-style: none; padding: 0; }
.site-map-list li { padding: 10px 0; border-bottom: 1px solid var(--line); font-size: 12px; }
.site-map-list small { display: block; margin-top: 4px; color: #888; font-size: 10px; }

.footer { background: var(--dark); color: #f8f6f1; padding: 30px 24px; }
.footer-inner { max-width: var(--width); margin: auto; display: flex; align-items: flex-start; justify-content: space-between; gap: 25px; flex-wrap: wrap; }
.footer-brand { font: 800 28px var(--serif); }
.footer-brand span { color: #f06a70; }
.footer-inner p { color: #c1c1c1; font-size: 11px; line-height: 1.6; }
.footer-links { display: flex; flex-wrap: wrap; gap: 12px 18px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.footer-links a:hover { color: #ff8b90; }

.progress { position: fixed; z-index: 20; top: 0; left: 0; width: 0; height: 3px; background: var(--red); }
.to-top { position: fixed; z-index: 15; right: 18px; bottom: 18px; width: 40px; height: 40px; border: 0; border-radius: 50%; background: var(--red); color: #fff; font-size: 19px; cursor: pointer; box-shadow: 0 3px 14px #0003; }
body.dark {
  --paper: #151515; --surface: #222; --ink: #f5f3ee; --muted: #d0ccc4; --line: #484848;
}
body.dark .masthead, body.dark .primary-nav, body.dark .story-card, body.dark .lead-story,
body.dark .explore-panel, body.dark .info-card, body.dark .mode-button, body.dark .track-controls button {
  background: var(--surface); color: var(--ink);
}
body.dark .section-chip { background: #303030; border-color: #484848; color: #f5f3ee; }
body.dark .lead-image, body.dark .story-image, body.dark .article-figure { background: #282828; }
body.dark .article-body { color: #f0eee8; }
body.dark .preliminary-note { background: #302a20; color: #f0e2c5; border-color: #d0a65d; }
body.dark .state-actualidad { background: #303b44; color: #d5e0e7; }
body.dark .state-confirmada { background: #233d2d; color: #a7e2b8; }
body.dark .state-desarrollo { background: #453923; color: #f0d49c; }
body.dark .state-preliminar { background: #482829; color: #f1b5b3; }
body.dark .mode-button:hover { background: #fff; color: #151515; }

@media (max-width: 980px) {
  .lead-layout { grid-template-columns: 1fr; }
  .lead-story { grid-template-columns: minmax(0, 1fr) minmax(260px, .9fr); }
  .lead-image { min-height: 300px; }
  .explore-panel { display: grid; grid-template-columns: 1fr 1fr; align-items: start; gap: 12px 18px; }
  .explore-panel > * { grid-column: 1 / -1; }
  .panel-links { grid-template-columns: 1fr 1fr; gap: 18px; }
  .story-card { flex-basis: clamp(340px, 42vw, 440px); }
}
@media (max-width: 700px) {
  .topline-inner { padding: 6px 15px; font-size: 8px; }
  .topline-inner span:nth-child(2) { display: none; }
  .brand-row { padding: 18px 15px 14px; gap: 10px; flex-wrap: wrap; }
  .brand-name { font-size: clamp(39px, 10vw, 48px); letter-spacing: -2.4px; }
  .brand-tagline { font-size: 8px; letter-spacing: 1.6px; }
  .brand-social { margin-left: auto; font-size: 10px; }
  .brand-social svg { width: 22px; height: 22px; }
  .brand-social small { font-size: 9px; }
  .edition { display: none; }
  .nav-inner { padding: 0 15px; }
  .nav-inner a { min-height: 42px; padding: 0 12px; font-size: 9px; }
  .toolbar { padding: 9px 15px; gap: 8px; }
  .search { flex: 1; }
  .search input { padding: 9px; font-size: 11px; }
  .mode-button { padding: 9px; white-space: nowrap; font-size: 9px; }
  .page { padding: 0 15px 35px; }
  .section-kicker { margin: 18px 0 12px; }
  .lead-story { grid-template-columns: 1fr; }
  .lead-image { min-height: 0; aspect-ratio: 16 / 9; }
  .lead-copy { padding: 18px 17px 20px; }
  .lead-copy h1 { font-size: clamp(27px, 8vw, 36px); }
  .lead-copy p { font-size: 12px; }
  .explore-panel { display: flex; padding: 17px; gap: 11px; }
  .explore-panel h2 { font-size: 23px; }
  .section-links { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panel-links { grid-template-columns: 1fr 1fr; }
  .category-block { margin-top: 26px; padding-top: 18px; }
  .category-heading h2 { font-size: 26px; }
  .news-track { gap: 12px; margin-right: -15px; padding-right: 15px; }
  .story-card { flex-basis: 84vw; }
  .story-copy { padding: 12px 13px 14px; }
  .story-copy h3 { font-size: 19px; }
  .story-copy p { font-size: 11px; }
  .article-page { margin-top: 25px; padding: 0 17px; }
  .article-page h1 { font-size: clamp(34px, 9vw, 44px); }
  .article-figure img { max-height: 60vh; }
  .editorial-page { padding: 32px 17px 48px; }
  .editorial-page h1 { font-size: clamp(36px, 10vw, 48px); }
  .editorial-intro { font-size: 15px; }
  .info-grid, .site-map-grid, .related-grid { grid-template-columns: 1fr; }
  .newsletter-item { grid-template-columns: 1fr; gap: 6px; }
  .footer { padding: 25px 17px; }
  .footer-inner { display: block; }
  .footer-links { margin-top: 18px; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
"""

SCRIPT = r"""
(function () {
  const root = document.body;
  const themeButton = document.getElementById("mode-toggle");
  try {
    if (localStorage.getItem("cev-theme") === "dark") root.classList.add("dark");
  } catch (_) {}
  function refreshThemeButton() {
    if (!themeButton) return;
    const dark = root.classList.contains("dark");
    themeButton.textContent = dark ? "☀ Modo claro" : "◐ Modo oscuro";
    themeButton.setAttribute("aria-pressed", String(dark));
  }
  refreshThemeButton();
  if (themeButton) themeButton.addEventListener("click", function () {
    root.classList.toggle("dark");
    try { localStorage.setItem("cev-theme", root.classList.contains("dark") ? "dark" : "light"); } catch (_) {}
    refreshThemeButton();
  });

  const search = document.getElementById("news-search");
  if (search) search.addEventListener("input", function () {
    const query = search.value.trim().toLocaleLowerCase("es");
    document.querySelectorAll(".story-card, .lead-story").forEach(function (card) {
      card.hidden = !!query && !card.innerText.toLocaleLowerCase("es").includes(query);
    });
    document.querySelectorAll(".category-block").forEach(function (section) {
      section.hidden = !!query && section.querySelectorAll(".story-card:not([hidden])").length === 0;
    });
  });

  document.querySelectorAll("[data-auto-carousel]").forEach(function (track) {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let paused = false;
    let previousTime = 0;
    let direction = 1;
    let resumeTimer = null;
    let lastPosition = track.scrollLeft;
    const speed = 34;
    function pause() {
      paused = true;
      previousTime = 0;
      if (resumeTimer) clearTimeout(resumeTimer);
    }
    function resumeSoon() {
      if (resumeTimer) clearTimeout(resumeTimer);
      resumeTimer = setTimeout(function () { paused = false; previousTime = 0; }, 1100);
    }
    track.addEventListener("mouseenter", pause);
    track.addEventListener("mouseleave", function () { paused = false; previousTime = 0; });
    track.addEventListener("focusin", pause);
    track.addEventListener("focusout", resumeSoon);
    track.addEventListener("pointerdown", pause, { passive: true });
    window.addEventListener("pointerup", resumeSoon, { passive: true });
    track.addEventListener("touchstart", pause, { passive: true });
    track.addEventListener("touchend", resumeSoon, { passive: true });
    track.addEventListener("wheel", function () { pause(); resumeSoon(); }, { passive: true });
    function animate(time) {
      if (!previousTime) previousTime = time;
      const delta = Math.min((time - previousTime) / 1000, 0.05);
      previousTime = time;
      const maximum = Math.max(0, track.scrollWidth - track.clientWidth);
      if (!paused && maximum > 8) {
        if (Math.abs(track.scrollLeft - lastPosition) > 2) direction = track.scrollLeft > lastPosition ? 1 : -1;
        let next = track.scrollLeft + direction * speed * delta;
        if (next >= maximum) { next = maximum; direction = -1; }
        if (next <= 0) { next = 0; direction = 1; }
        track.scrollLeft = next;
      }
      lastPosition = track.scrollLeft;
      window.requestAnimationFrame(animate);
    }
    window.requestAnimationFrame(animate);
  });

  const progress = document.getElementById("read-progress");
  const topButton = document.getElementById("back-top");
  function updateScrollTools() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    if (progress) progress.style.width = (max > 0 ? window.scrollY / max * 100 : 0) + "%";
    if (topButton) topButton.hidden = window.scrollY < 400;
  }
  window.addEventListener("scroll", updateScrollTools, { passive: true });
  updateScrollTools();
  if (topButton) topButton.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });

  document.querySelectorAll("[data-track-left]").forEach(function (button) {
    button.addEventListener("click", function () {
      const track = document.getElementById(button.getAttribute("data-track-left"));
      if (track) track.scrollBy({ left: -track.clientWidth * 0.8, behavior: "smooth" });
    });
  });
  document.querySelectorAll("[data-track-right]").forEach(function (button) {
    button.addEventListener("click", function () {
      const track = document.getElementById(button.getAttribute("data-track-right"));
      if (track) track.scrollBy({ left: track.clientWidth * 0.8, behavior: "smooth" });
    });
  });
})();
"""


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS", ruta_raiz="", extra_head=""):
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", []) if isinstance(datos, dict) else []
    disponibles = set(SECCIONES_DISPONIBLES) if SECCIONES_DISPONIBLES else {n.get("categoria") for n in noticias if isinstance(n, dict)}
    enlaces_seccion = "".join(
        f'<a href="https://cevnoticias.com/#categoria-{slug(seccion)}">{escapar(seccion)}</a>'
        for seccion in SECCIONES if seccion in disponibles
    )
    raiz = ruta_raiz or ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f5f4f0">
<meta name="description" content="{escapar(descripcion)}">
{extra_head}
<title>{escapar(titulo)} | CEV NOTICIAS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="topline"><div class="topline-inner"><strong>CEV NOTICIAS</strong><span>Periodismo · Contexto · Actualidad</span><span>{fecha_actual()} · Cali, Colombia</span></div></div>
<header class="masthead">
  <div class="brand-row">
    <div><div class="brand-name"><a href="https://cevnoticias.com/">CEV <span>NOTICIAS</span></a></div><div class="brand-tagline">La actualidad, con contexto.</div></div>
    <a class="brand-social" href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer" aria-label="Instagram CEV Noticias">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.5" cy="6.8" r="1.1" fill="currentColor"/></svg>
      <span><strong>Cali en Vivo Noticias</strong><small>@cev.noticias</small></span>
    </a>
    <div class="edition">Edición digital<br>Actualización permanente</div>
  </div>
  <nav class="primary-nav" aria-label="Navegación principal">
    <div class="nav-inner"><a href="https://cevnoticias.com/">Portada</a>{enlaces_seccion}<a class="nav-page" href="{raiz}institucional.html">Quiénes somos</a><a class="nav-page" href="{raiz}boletin.html">Boletín</a><a class="nav-page" href="{raiz}mapa-del-sitio.html">Mapa del sitio</a></div>
  </nav>
  <div class="toolbar">
    <label class="search"><input id="news-search" type="search" placeholder="Buscar noticias o temas..." aria-label="Buscar noticias"></label>
    <button class="mode-button" id="mode-toggle" type="button" aria-pressed="false">◐ Modo oscuro</button>
  </div>
</header>
{contenido}
<footer class="footer">
  <div class="footer-inner">
    <div><div class="footer-brand">CEV <span>NOTICIAS</span></div><p>Actualidad de Cali, el Valle del Cauca, Colombia y el mundo.</p></div>
    <nav class="footer-links" aria-label="Enlaces del pie"><a href="https://cevnoticias.com/">Portada</a><a href="{raiz}institucional.html">Quiénes somos</a><a href="{raiz}boletin.html">Boletín</a><a href="{raiz}mapa-del-sitio.html">Mapa del sitio</a><a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Instagram</a></nav>
  </div>
</footer>
<div class="progress" id="read-progress"></div>
<button class="to-top" id="back-top" type="button" aria-label="Volver arriba" hidden>↑</button>
<script>{SCRIPT}</script>
</body>
</html>"""


def tarjeta(noticia, en_articulo=False):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    identificador = escapar(noticia.get("id"))
    destino = f"{identificador}.html" if en_articulo else f"notas/{identificador}.html"
    imagen = imagen_segura(noticia.get("imagen"))
    visual = f'<img src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else '<div class="story-image">CEV NOTICIAS</div>'
    return f"""
    <article class="story-card">
      <a class="story-link" href="{destino}">
        <div class="story-image">{visual}</div>
        <div class="story-copy">
          <span class="category-label">{categoria}</span>
          <div class="state-wrap">{etiqueta_estado(noticia)}</div>
          <h3>{titulo}</h3>
          <p>{resumen}</p>
          <span class="read-more">Leer noticia completa ↗</span>
        </div>
      </a>
    </article>"""


def crear_articulo(noticia, noticias):
    ident = str(noticia["id"])
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    imagen = imagen_segura(noticia.get("imagen"))
    contenido = str(noticia.get("contenido") or "").strip()
    foto = f'<figure class="article-figure"><img src="{imagen}" alt="{titulo}" loading="lazy"></figure>' if imagen else ""
    parrafos = "".join(f"<p>{escapar(parrafo.strip())}</p>" for parrafo in contenido.split("\n\n") if parrafo.strip())

    credito = noticia.get("imagen_credito") or {}
    atribucion = ""
    if imagen and credito:
        autor = escapar(credito.get("autor", "Autor no identificado"))
        origen = escapar(credito.get("fuente", "Archivo de imágenes"))
        licencia = escapar(credito.get("licencia", "Consultar licencia"))
        pagina_imagen = imagen_segura(credito.get("pagina", ""))
        licencia_url = imagen_segura(credito.get("licencia_url", ""))
        extras = []
        if pagina_imagen:
            extras.append(f'<a href="{pagina_imagen}" target="_blank" rel="noopener noreferrer">fuente original</a>')
        if licencia_url:
            extras.append(f'<a href="{licencia_url}" target="_blank" rel="noopener noreferrer">licencia</a>')
        atribucion = f'<p class="image-credit">Imagen: {autor} · {origen} · {licencia} {" · ".join(extras)}</p>'

    refs = [f"<li>{escapar(fuente.get('nombre', 'Fuente consultada'))}</li>" for fuente in noticia.get("fuentes", [])]
    estado = noticia.get("estado_informacion")
    nota_preliminar = ""
    if estado in ("en_desarrollo", "informacion_preliminar"):
        nota_preliminar = '<p class="preliminary-note">La información disponible es preliminar y puede cambiar. Se actualizará cuando existan nuevos datos respaldados por fuentes confiables.</p>'

    palabras = lambda text: set(re.findall(r"[a-záéíóúñü]{4,}", str(text or "").lower()))
    base = palabras(str(noticia.get("titulo", "")) + " " + str(noticia.get("resumen", "")))
    relacionadas = []
    for otra in noticias:
        if otra.get("id") == noticia.get("id"):
            continue
        comunes = len(base & palabras(str(otra.get("titulo", "")) + " " + str(otra.get("resumen", ""))))
        puntaje = comunes + (2 if otra.get("categoria") == noticia.get("categoria") else 0)
        if puntaje:
            relacionadas.append((puntaje, otra))
    relacionadas.sort(key=lambda item: item[0], reverse=True)
    rel = ""
    if relacionadas:
        rel = '<section class="related"><h2>También te puede interesar</h2><div class="related-grid">' + "".join(tarjeta(n, en_articulo=True) for _, n in relacionadas[:2]) + "</div></section>"

    cuerpo = f"""
    <main class="article-page">
      <header class="article-header">
        <a class="back-link" href="https://cevnoticias.com/">← Volver a portada</a>
        <div class="category-label">{categoria}</div>
        <div class="state-wrap">{etiqueta_estado(noticia)}</div>
        <h1>{titulo}</h1>
        <p class="article-summary">{resumen}</p>
        <div class="article-meta">Publicado: {escapar(noticia.get("fecha", fecha_actual()))} · CEV NOTICIAS</div>
        {nota_preliminar}
      </header>
      {foto}{atribucion}
      <div class="article-body">{parrafos}</div>
      <section class="sources"><strong>Fuentes consultadas</strong><ul>{''.join(refs)}</ul><p>Artículo de elaboración propia. Consulta las fuentes relacionadas para ampliar la información.</p></section>
      {rel}
    </main>"""
    url = f"https://cevnoticias.com/notas/{ident}.html"
    schema = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": str(noticia.get("titulo", "")),
        "description": str(noticia.get("resumen", "")),
        "author": {"@type": "Organization", "name": "CEV NOTICIAS"},
        "publisher": {"@type": "Organization", "name": "CEV NOTICIAS"},
        "mainEntityOfPage": url
    }
    if imagen:
        schema["image"] = imagen
    extra = (
        f'<link rel="canonical" href="{url}">'
        f'<meta property="og:type" content="article">'
        f'<meta property="og:title" content="{titulo}">'
        f'<meta property="og:description" content="{resumen}">'
        f'<meta property="og:url" content="{url}">'
        + (f'<meta property="og:image" content="{imagen}">' if imagen else "")
        + '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + "</script>"
    )
    pagina = plantilla(titulo, cuerpo, resumen, ruta_raiz="../", extra_head=extra)
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"{ident}.html").write_text(pagina, encoding="utf-8")


def crear_pagina_institucional():
    contenido = """
    <main class="editorial-page">
      <div class="eyebrow">Conoce nuestro medio</div>
      <h1>Información con contexto.</h1>
      <p class="editorial-intro">CEV NOTICIAS es el espacio informativo de Cali en Vivo. Reunimos actualidad de Cali, el Valle del Cauca, Colombia y el mundo, distinguiendo los hechos confirmados de la información que continúa en desarrollo.</p>
      <div class="info-grid">
        <section class="info-card"><h2>Qué hacemos</h2><p>Publicamos información de interés público en ciudad, región, país, mundo, economía, deportes y tecnología. Cada noticia presenta titular, resumen y el contexto disponible.</p></section>
        <section class="info-card"><h2>Criterios editoriales</h2><ul><li>Separar hechos conocidos de versiones iniciales.</li><li>Atribuir la información a las fuentes consultadas.</li><li>No presentar rumores como hechos.</li><li>Actualizar publicaciones con nuevos datos respaldados.</li></ul></section>
        <section class="info-card"><h2>Estados de la información</h2><p><strong>Actualidad:</strong> publicación sin una marca específica de seguimiento.</p><p><strong>Confirmada:</strong> los datos centrales cuentan con respaldo suficiente en las fuentes consultadas.</p><p><strong>En desarrollo:</strong> el hecho sigue evolucionando.</p><p><strong>Información preliminar:</strong> los primeros datos todavía requieren confirmación.</p></section>
        <section class="info-card"><h2>Fuentes y correcciones</h2><p>Las fuentes consultadas se identifican al final de cada artículo. Para comunicar una corrección o actualización, escribe al equipo editorial.</p><p><a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Contactar a CEV NOTICIAS ↗</a></p></section>
      </div>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/institucional.html"><meta property="og:title" content="Quiénes somos | CEV NOTICIAS"><meta property="og:type" content="website">'
    (SITE / "institucional.html").write_text(
        plantilla("Quiénes somos", contenido, "Conoce CEV NOTICIAS y sus criterios editoriales.", extra_head=extra),
        encoding="utf-8"
    )


def crear_pagina_boletin(noticias):
    elementos = []
    for noticia in noticias[:12]:
        elementos.append(
            f'<article class="newsletter-item"><time>{escapar(noticia.get("fecha", ""))}</time>'
            f'<div><span class="category-label">{escapar(noticia.get("categoria"))}</span>'
            f'<div class="state-wrap">{etiqueta_estado(noticia)}</div>'
            f'<h2><a href="notas/{escapar(noticia.get("id"))}.html">{escapar(noticia.get("titulo"))}</a></h2>'
            f'<p>{escapar(noticia.get("resumen"))}</p></div></article>'
        )
    contenido = f"""
    <main class="editorial-page">
      <div class="eyebrow">Boletín informativo</div>
      <h1>Lo esencial, sin perder el contexto.</h1>
      <p class="editorial-intro">Resumen de las noticias más recientes publicadas por CEV NOTICIAS. Esta página se actualiza junto con la edición digital.</p>
      <p class="article-meta">Actualizado: {fecha_actual()}</p>
      <section class="newsletter-list">{''.join(elementos) if elementos else '<p>Aún no hay publicaciones disponibles.</p>'}</section>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/boletin.html"><meta property="og:title" content="Boletín de noticias | CEV NOTICIAS"><meta property="og:type" content="website">'
    (SITE / "boletin.html").write_text(
        plantilla("Boletín de noticias", contenido, "Resumen de las noticias más recientes de CEV NOTICIAS.", extra_head=extra),
        encoding="utf-8"
    )


def crear_mapa_sitio(noticias):
    secciones = []
    for seccion in SECCIONES:
        if any(n.get("categoria") == seccion for n in noticias):
            secciones.append(f'<li><a href="https://cevnoticias.com/#categoria-{slug(seccion)}">{escapar(seccion)}</a></li>')
    articulos = "".join(
        f'<li><a href="notas/{escapar(n.get("id"))}.html">{escapar(n.get("titulo"))}</a><small>{escapar(n.get("categoria"))} · {escapar(n.get("fecha", ""))}</small></li>'
        for n in noticias
    )
    contenido = f"""
    <main class="editorial-page">
      <div class="eyebrow">Navegación</div><h1>Mapa del sitio</h1>
      <p class="editorial-intro">Encuentra las páginas, secciones y artículos de CEV NOTICIAS.</p>
      <div class="site-map-grid">
        <section class="info-card"><h2>Páginas principales</h2><ul class="site-map-list"><li><a href="https://cevnoticias.com/">Portada</a></li><li><a href="institucional.html">Quiénes somos</a></li><li><a href="boletin.html">Boletín de noticias</a></li></ul></section>
        <section class="info-card"><h2>Secciones</h2><ul class="site-map-list">{''.join(secciones)}</ul></section>
        <section class="info-card" style="grid-column:1/-1"><h2>Artículos publicados</h2><ul class="site-map-list">{articulos}</ul></section>
      </div>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/mapa-del-sitio.html"><meta property="og:title" content="Mapa del sitio | CEV NOTICIAS"><meta property="og:type" content="website">'
    (SITE / "mapa-del-sitio.html").write_text(
        plantilla("Mapa del sitio", contenido, "Mapa de páginas y artículos de CEV NOTICIAS.", extra_head=extra),
        encoding="utf-8"
    )


def construir():
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", []) if isinstance(datos, dict) else []
    validas = []
    vistos_ids = set()
    vistos_titulos = set()

    for noticia in noticias:
        if not isinstance(noticia, dict):
            continue
        titulo = str(noticia.get("titulo", "")).strip()
        cuerpo = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")
        if not titulo or len(cuerpo) < 250 or categoria not in SECCIONES or not imagen_segura(noticia.get("imagen")):
            continue
        ident = str(noticia.get("id") or slug(titulo))
        titulo_normalizado = re.sub(r"[^a-z0-9]+", " ", titulo.lower()).strip()
        if ident in vistos_ids or titulo_normalizado in vistos_titulos:
            continue
        noticia["id"] = ident
        noticia.setdefault("fecha", fecha_actual())
        noticia.setdefault("resumen", cuerpo[:220])
        noticia.setdefault("fuentes", [])
        validas.append(noticia)
        vistos_ids.add(ident)
        vistos_titulos.add(titulo_normalizado)

    global SECCIONES_DISPONIBLES
    SECCIONES_DISPONIBLES = [seccion for seccion in SECCIONES if any(n.get("categoria") == seccion for n in validas)]

    SITE.mkdir(parents=True, exist_ok=True)
    NOTAS.mkdir(parents=True, exist_ok=True)

    for noticia in validas:
        crear_articulo(noticia, validas)
    crear_pagina_institucional()
    crear_pagina_boletin(validas)
    crear_mapa_sitio(validas)

    principal = validas[0] if validas else None
    if principal:
        imagen = imagen_segura(principal.get("imagen"))
        imagen_html = f'<img src="{imagen}" alt="{escapar(principal.get("titulo"))}" fetchpriority="high">' if imagen else ""
        hero = f"""
        <article class="lead-story" id="categoria-{slug(principal.get('categoria'))}">
          <div class="lead-image">{imagen_html}</div>
          <div class="lead-copy">
            <span class="category-label">{escapar(principal.get('categoria'))} · NOTICIA DESTACADA</span>
            <div class="state-wrap">{etiqueta_estado(principal)}</div>
            <h1>{escapar(principal.get('titulo'))}</h1>
            <p>{escapar(principal.get('resumen'))}</p>
            <div class="story-meta">{escapar(principal.get('fecha', fecha_actual()))} · CEV NOTICIAS</div>
            <a class="read-link" href="notas/{escapar(principal.get('id'))}.html">Leer noticia completa ↗</a>
          </div>
        </article>"""
        categoria_destacada = principal.get("categoria")
    else:
        hero = '<article class="lead-story"><div class="lead-copy"><h1>CEV NOTICIAS</h1><p>Estamos preparando las próximas publicaciones.</p></div></article>'
        categoria_destacada = None

    conteos = {seccion: sum(1 for n in validas if n.get("categoria") == seccion) for seccion in SECCIONES}
    chips = "".join(
        f'<a class="section-chip" href="https://cevnoticias.com/#categoria-{slug(seccion)}"><span>{escapar(seccion)}</span><small>{conteos[seccion]}</small></a>'
        for seccion in SECCIONES if conteos[seccion]
    )
    panel = f"""
    <aside class="explore-panel">
      <div class="panel-overline">CEV · GUÍA DE LECTURA</div>
      <h2>Explora por secciones</h2>
      <p>Elige un tema y accede directamente a sus publicaciones.</p>
      <div class="section-links">{chips}</div>
      <div class="panel-links"><a href="institucional.html">Conoce nuestro medio ↗</a><a href="boletin.html">Ver el boletín ↗</a></div>
    </aside>"""

    layout = f"""
    <main class="page">
      <div class="section-kicker">Primera plana <span>{fecha_actual()}</span></div>
      <section class="lead-layout">{hero}{panel}</section>
      {''.join(bloques_categoria(validas, categoria_destacada))}
    </main>"""
    if not validas:
        layout = '<main class="page"><p class="section-kicker">Primera plana</p><p>No hay noticias disponibles en este momento.</p></main>'

    schema = {
        "@context": "https://schema.org",
        "@type": "NewsMediaOrganization",
        "name": "CEV NOTICIAS",
        "url": "https://cevnoticias.com/",
        "sameAs": ["https://www.instagram.com/cev.noticias/"],
        "description": "Noticias de Cali, Valle del Cauca, Colombia y el mundo."
    }
    extra = (
        '<link rel="canonical" href="https://cevnoticias.com/">'
        '<meta property="og:type" content="website">'
        '<meta property="og:title" content="CEV NOTICIAS | Actualidad y periodismo">'
        '<meta property="og:description" content="Noticias de Cali, Valle del Cauca, Colombia y el mundo.">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + "</script>"
    )
    (SITE / "index.html").write_text(
        plantilla("Portada", layout, "Noticias de Cali, Valle del Cauca, Colombia y el mundo.", extra_head=extra),
        encoding="utf-8"
    )

    urls = [
        "https://cevnoticias.com/",
        "https://cevnoticias.com/institucional.html",
        "https://cevnoticias.com/boletin.html",
        "https://cevnoticias.com/mapa-del-sitio.html"
    ] + [f"https://cevnoticias.com/notas/{n['id']}.html" for n in validas]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"<url><loc>{html.escape(url)}</loc></url>\n" for url in urls)
    sitemap += "</urlset>\n"
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://cevnoticias.com/sitemap.xml\n",
        encoding="utf-8"
    )
    print(f"Portada creada. Artículos publicados: {len(validas)}")


def bloques_categoria(noticias, categoria_destacada):
    bloques = []
    por_seccion = {}
    for noticia in noticias:
        if noticia.get("categoria") == categoria_destacada and noticia.get("id") == (noticias[0].get("id") if noticias else None):
            continue
        por_seccion.setdefault(noticia.get("categoria", "Actualidad"), []).append(noticia)

    for seccion in SECCIONES:
        grupo = por_seccion.get(seccion, [])
        if not grupo:
            continue
        identificador = f"categoria-{slug(seccion)}"
        if seccion == categoria_destacada:
            identificador += "-mas"
        tarjetas = "".join(tarjeta(noticia) for noticia in grupo)
        controles = ""
        if len(grupo) > 1:
            controles = f'<div class="track-controls"><button type="button" data-track-left="{identificador}-track" aria-label="Mover a la izquierda">‹</button><button type="button" data-track-right="{identificador}-track" aria-label="Mover a la derecha">›</button></div>'
        carrusel = f'<div class="news-track" id="{identificador}-track" data-auto-carousel>{tarjetas}</div>' if len(grupo) > 1 else f'<div class="news-track">{tarjetas}</div>'
        bloques.append(
            f'<section class="category-block" id="{identificador}">'
            f'<div class="category-heading"><h2>{escapar(seccion)}</h2><a href="https://cevnoticias.com/#categoria-{slug(seccion)}">Ver sección</a></div>'
            f'{carrusel}{controles}</section>'
        )
    return "".join(bloques)


if __name__ == "__main__":
    construir()
