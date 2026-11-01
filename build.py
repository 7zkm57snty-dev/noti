import html, json, re, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import redactor

CATEGORIAS = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología"]
POR_CATEGORIA = 8
MAX_HORAS = 72
BOGOTA = timezone(timedelta(hours=-5))
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def esc(t):
    return html.escape(str(t or ""), quote=True)

def sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(t)).strip("-")

def palabras(t):
    return {w for w in re.findall(r"[a-z0-9]+", sin_tildes(t)) if len(w) > 3}

def limpiar(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()

def fecha_de(txt):
    try:
        d = parsedate_to_datetime((txt or "").strip())
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def url_de(feed):
    if feed.get("gnews"):
        q = urllib.parse.urlencode({"q": feed["gnews"], "hl": "es-419", "gl": "CO", "ceid": "CO:es-419"})
        return "https://news.google.com/rss/search?" + q
    return feed["url"]

def descargar(feed):
    nombre = feed.get("fuente") or feed.get("gnews") or feed.get("url")
    try:
        req = urllib.request.Request(url_de(feed), headers={"User-Agent": "Mozilla/5.0 (compatible; CEVNoticias/2.0)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raiz = ET.fromstring(r.read())
    except Exception as e:
        print(f"FALLO RSS {nombre}: {e}")
        return []
    ahora, salida = datetime.now(timezone.utc), []
    for it in raiz.iter():
        if it.tag.split("}")[-1] != "item":
            continue
        fecha = fecha_de(it.findtext("pubDate"))
        enlace = (it.findtext("link") or "").strip()
        titulo = limpiar(it.findtext("title"))
        if not (fecha and enlace.startswith("http") and titulo):
            continue
        if ahora - fecha > timedelta(hours=MAX_HORAS) or fecha > ahora + timedelta(hours=1):
            continue
        src = next((x for x in it if x.tag.split("}")[-1] == "source"), None)
        dominio = urllib.parse.urlparse(src.get("url", "") if src is not None else "").netloc.lower()
        permitidos = [x.lower() for x in feed.get("permitidos", [])]
        if permitidos and not any(dominio == p or dominio.endswith("." + p) for p in permitidos):
            continue
        fuente = feed.get("fuente") or (limpiar(src.text) if src is not None else "")
        if not fuente:
            continue
        sufijo = " - " + fuente
        if titulo.endswith(sufijo):
            titulo = titulo[:-len(sufijo)].strip()
        resumen = limpiar(it.findtext("description"))[:700]
        salida.append({"cat": feed["categoria"], "fuente": fuente, "titulo": titulo,
                       "link": enlace, "fecha": fecha.isoformat(), "resumen": resumen})
    print(f"RSS {nombre}: {len(salida)} noticias")
    return salida

def hace(fecha, ahora):
    m = max(1, int((ahora-fecha).total_seconds()//60))
    return f"hace {m} min" if m < 60 else (f"hace {m//60} h" if m < 1440 else f"hace {m//1440} d")

def tarjeta(n, ahora, clase="card"):
    propia = bool(n.get("propia"))
    img = redactor.svg(n["titulo"], n["cat"]) if propia else ""
    target = "" if propia else ' target="_blank" rel="noopener noreferrer"'
    resumen = f'<p>{esc(n.get("resumen", ""))}</p>' if n.get("resumen") else ""
    return (f'<article class="{clase}">{img}<span class="cat">{esc(n["cat"])}</span>'
            f'<h3><a href="{esc(n["link"])}"{target}>{esc(n["titulo"])}</a></h3>{resumen}'
            f'<div class="meta"><b>{esc(n["fuente"])}</b> · {hace(n["_fecha"], ahora)}</div></article>')

CSS = """
:root{--ac:#b3121e;--fg:#171717;--mut:#5b5b5b;--line:#dedede}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:inherit;text-decoration:none}.wrap{max-width:1120px;margin:auto;padding:0 18px}
header{border-top:8px solid var(--ac);text-align:center;padding:22px 0 16px}
.marca{font:700 clamp(38px,8vw,72px)/1 Georgia,serif;margin:0}.fecha{color:var(--mut);font-size:14px;margin-top:10px}
nav{position:sticky;top:0;background:#fff;border-block:1px solid var(--line);overflow-x:auto;white-space:nowrap;text-align:center;z-index:5}
nav a{display:inline-block;padding:12px 15px;font-weight:650}section{margin-top:34px;scroll-margin-top:60px}
h2{font:700 27px/1.2 Georgia,serif;margin:0 0 17px;padding-left:12px;border-left:6px solid var(--ac)}
h3{font:700 20px/1.3 Georgia,serif;margin:0 0 7px}.grid{display:grid;gap:22px 24px;grid-template-columns:repeat(auto-fill,minmax(265px,1fr))}
.card{padding-bottom:16px;border-bottom:1px solid var(--line)}.portada{display:grid;gap:28px;grid-template-columns:3fr 2fr;margin-top:28px}
.principal{padding-bottom:18px;border-bottom:1px solid var(--line)}.principal h3{font-size:clamp(28px,4.5vw,43px);line-height:1.15}
p{margin:0 0 9px;color:var(--mut)}.cat{display:block;color:var(--ac);font-size:13px;font-weight:750;margin-bottom:5px}
.meta{font-size:13px;color:var(--mut)}.meta b{color:var(--fg);margin-right:8px}
footer{margin-top:42px;border-top:1px solid var(--fg);padding:22px 0 48px;color:var(--mut);font-size:14px}
.card svg,.principal svg{width:100%;height:auto;display:block;margin-bottom:9px}
@media(max-width:780px){.portada{grid-template-columns:1fr}}
"""

def pagina(por_cat, portada, ahora):
    loc = ahora.astimezone(BOGOTA)
    fecha = f"{DIAS[loc.weekday()]}, {loc.day} de {MESES[loc.month-1]} de {loc.year}. Actualizado a las {loc.hour%12 or 12}:{loc.minute:02d} {'a. m.' if loc.hour<12 else 'p. m.'}"
    nav = "".join(f'<a href="#{slug(c)}">{esc(c)}</a>' for c in CATEGORIAS)
    cuerpo = ""
    if portada:
        lateral = "".join(tarjeta(n, ahora) for n in portada[1:])
        cuerpo += f'<div class="portada"><div class="principal">{tarjeta(portada[0], ahora, "principal-card")}</div><div>{lateral}</div></div>'
    for c in CATEGORIAS:
        notas = por_cat[c]
        interior = "".join(tarjeta(n, ahora) for n in notas) if notas else '<p>No hay noticias nuevas en las últimas 72 horas.</p>'
        cuerpo += f'<section id="{slug(c)}"><h2>{esc(c)}</h2><div class="grid">{interior}</div></section>'
    pie = '<footer><h2>Acerca de CEV NOTICIAS</h2>Publicamos artículos originales cuando se recupera información suficiente de más de una fuente. Las fuentes consultadas se enlazan al final de cada artículo.</footer>'
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>CEV NOTICIAS</title><meta name="description" content="Noticias de Cali, Valle del Cauca, Colombia y el mundo.">'
            f'<style>{CSS}</style></head><body><header><h1 class="marca">CEV NOTICIAS</h1><div class="fecha">{esc(fecha)}</div></header>'
            f'<nav>{nav}</nav><main class="wrap">{cuerpo}{pie}</main></body></html>')

def main():
    feeds = json.loads(Path("feeds.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=4) as ex:
        listas = list(ex.map(descargar, feeds))
    vistos, notas = set(), []
    for lista in listas:
        for n in lista:
            clave = (n["fuente"].lower(), n["titulo"].lower())
            if n["link"] in vistos or clave in vistos:
                continue
            vistos.add(n["link"]); vistos.add(clave)
            n["_fecha"] = datetime.fromisoformat(n["fecha"])
            notas.append(n)
    if not notas:
        raise SystemExit("No se encontraron noticias RSS válidas; se conserva la versión anterior.")
    ahora = datetime.now(timezone.utc)
    propias, reemplazadas = redactor.generar(notas, CSS, ahora)
    notas = [n for n in notas if id(n) not in reemplazadas] + propias
    por_cat = {c: sorted([n for n in notas if n["cat"] == c], key=lambda n:n["_fecha"], reverse=True)[:POR_CATEGORIA] for c in CATEGORIAS}
    visibles = [n for c in CATEGORIAS for n in por_cat[c]]
    portada = sorted(visibles, key=lambda n:(bool(n.get("propia")), n["_fecha"]), reverse=True)[:5]
    Path("site").mkdir(exist_ok=True)
    Path("site/index.html").write_text(pagina(por_cat, portada, ahora), encoding="utf-8")
    print(f"Sitio generado: {len(visibles)} noticias; {len(propias)} artículos propios.")

if __name__ == "__main__":
    main()
