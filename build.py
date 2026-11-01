"""CEV NOTICIAS: lee los RSS de feeds.json y genera site/index.html."""
import html, json, re, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

CONTACTO = ""  # Pon aquí tu correo si quieres que aparezca en el pie de página
CATEGORIAS = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología"]
POR_CATEGORIA = 8
MAX_HORAS = 72
BOGOTA = timezone(timedelta(hours=-5))
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def esc(t):
    return html.escape(t, quote=True)


def sin_tildes(t):
    t = unicodedata.normalize("NFD", t.lower())
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
    if "gnews" in feed:
        q = urllib.parse.urlencode({"q": feed["gnews"], "hl": "es-419", "gl": "CO", "ceid": "CO:es-419"})
        return "https://news.google.com/rss/search?" + q
    return feed["url"]


def descargar(feed):
    nombre = feed.get("fuente") or feed.get("gnews") or feed.get("url")
    try:
        req = urllib.request.Request(url_de(feed), headers={"User-Agent": "Mozilla/5.0 (compatible; CEVNoticias/1.0)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raiz = ET.fromstring(r.read())
    except Exception as e:
        print(f"FALLO {nombre}: {e}")
        return []
    ahora = datetime.now(timezone.utc)
    salida = []
    for it in raiz.iter("item"):
        fecha = fecha_de(it.findtext("pubDate"))
        enlace = (it.findtext("link") or "").strip()
        titulo = limpiar(it.findtext("title"))
        if not (fecha and enlace.startswith("http") and titulo):
            continue
        if ahora - fecha > timedelta(hours=MAX_HORAS) or fecha > ahora + timedelta(hours=1):
            continue
        src = it.find("source")
        fuente = feed.get("fuente") or (limpiar(src.text) if src is not None else "")
        if not fuente:
            continue
        if feed.get("permitidos"):  # lista blanca: solo medios aprobados
            dom = urllib.parse.urlparse(src.get("url", "") if src is not None else "").netloc.lower()
            if not any(dom == p or dom.endswith("." + p) for p in feed["permitidos"]):
                continue
        if titulo.endswith(" - " + fuente):
            titulo = titulo[: -len(fuente) - 3].strip()
        resumen = ""
        if feed.get("resumen"):
            r = limpiar(it.findtext("description"))
            if len(r) > 40 and not r.startswith(titulo[:30]):
                resumen = (r[:200].rsplit(" ", 1)[0] + "…") if len(r) > 200 else r
        salida.append({"cat": feed["categoria"], "fuente": fuente, "titulo": titulo,
                       "link": enlace, "fecha": fecha, "resumen": resumen})
    print(f"OK {nombre}: {len(salida)} notas")
    return salida


def marcar_confirmadas(notas):
    """Una nota queda confirmada si otro medio publica un titular muy parecido."""
    for a in notas:
        a["otras"] = set()
        for b in notas:
            if b["fuente"] == a["fuente"] or not a["pal"] or not b["pal"]:
                continue
            if len(a["pal"] & b["pal"]) / len(a["pal"] | b["pal"]) >= 0.5:
                a["otras"].add(b["fuente"])


def hace(d, ahora):
    m = int((ahora - d).total_seconds() // 60)
    if m < 60:
        return f"hace {max(m, 1)} min"
    if m < 1440:
        return f"hace {m // 60} h"
    return f"hace {m // 1440} d"


def tarjeta(n, ahora, clase="card"):
    ok = ""
    if n["otras"]:
        otros = ", ".join(sorted(n["otras"]))
        ok = f'<span class="ok" title="También lo reporta: {esc(otros)}">Confirmado por {1 + len(n["otras"])} medios</span>'
    res = f'<p>{esc(n["resumen"])}</p>' if n["resumen"] else ""
    return (f'<article class="{clase}"><span class="cat">{esc(n["cat"])}</span>'
            f'<h3><a href="{esc(n["link"])}" target="_blank" rel="noopener noreferrer">{esc(n["titulo"])}</a></h3>'
            f'{res}<div class="meta"><b>{esc(n["fuente"])}</b>{hace(n["fecha"], ahora)}</div>{ok}</article>')


CSS = """
:root{--ac:#b3121e;--fg:#000;--mut:#5b5b5b;--line:#d9d9d9;--ok:#0a6b36}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:inherit;text-decoration:none}
a:focus-visible{outline:3px solid var(--ac);outline-offset:2px}
h3 a:hover{color:var(--ac)}
.wrap{max-width:1100px;margin:0 auto;padding:0 18px}
header{border-top:8px solid var(--ac);text-align:center;padding:20px 0 14px}
.marca{font:700 clamp(38px,8vw,72px)/1 Georgia,"Times New Roman",serif;margin:0}
.fecha{color:var(--mut);font-size:14px;margin-top:8px}
nav{position:sticky;top:0;z-index:5;background:#fff;border-top:1px solid var(--fg);border-bottom:1px solid var(--line);overflow-x:auto;white-space:nowrap;text-align:center}
nav a{display:inline-block;padding:12px 16px;font-weight:600;font-size:15px}
nav a:hover{color:var(--ac)}
section{margin-top:34px;scroll-margin-top:56px}
h2{font:700 26px/1.2 Georgia,"Times New Roman",serif;margin:0 0 16px;padding-left:12px;border-left:6px solid var(--ac)}
h3{font:700 19px/1.3 Georgia,"Times New Roman",serif;margin:0 0 6px}
.grid{display:grid;gap:22px 24px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.card{padding-bottom:14px;border-bottom:1px solid var(--line)}
.portada{display:grid;gap:28px;grid-template-columns:3fr 2fr;margin-top:26px}
.principal{padding-bottom:18px;border-bottom:1px solid var(--line)}
.principal h3{font-size:clamp(28px,4.4vw,42px);line-height:1.15}
.lateral .card{margin-bottom:16px}
p{margin:0 0 8px;color:var(--mut)}
.cat{display:block;margin-bottom:4px;color:var(--ac);font-weight:700;font-size:13px}
.meta{font-size:13px;color:var(--mut)}
.meta b{color:var(--fg);margin-right:10px}
.ok{display:inline-block;margin-top:8px;color:var(--ok);border:1px solid var(--ok);border-radius:3px;padding:1px 7px;font-size:12px;font-weight:600}
.vacio{color:var(--mut)}
footer{margin-top:40px;border-top:1px solid var(--fg);padding:20px 0 48px;color:var(--mut);font-size:14px;max-width:70ch}
footer h2{font-size:18px;border:0;padding:0;margin:0 0 8px;color:var(--fg)}
@media(max-width:780px){.portada{grid-template-columns:1fr}}
@media(prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""


def pagina(por_cat, portada, ahora):
    loc = ahora.astimezone(BOGOTA)
    h12 = loc.hour % 12 or 12
    fecha = (f"{DIAS[loc.weekday()]}, {loc.day} de {MESES[loc.month - 1]} de {loc.year}. "
             f"Actualizado a las {h12}:{loc.minute:02d} {'a. m.' if loc.hour < 12 else 'p. m.'}")
    nav = "".join(f'<a href="#{slug(c)}">{esc(c)}</a>' for c in CATEGORIAS)
    cuerpo = ""
    if portada:
        lat = "".join(tarjeta(n, ahora) for n in portada[1:])
        cuerpo += (f'<div class="portada"><div class="principal">{tarjeta(portada[0], ahora, "")}</div>'
                   f'<div class="lateral">{lat}</div></div>')
    for c in CATEGORIAS:
        notas = por_cat[c]
        interior = "".join(tarjeta(n, ahora) for n in notas) if notas else \
            '<p class="vacio">No hay notas nuevas en las últimas 72 horas.</p>'
        cuerpo += f'<section id="{slug(c)}"><h2>{esc(c)}</h2><div class="grid">{interior}</div></section>'
    contacto = f" Para avisar de un error, escríbenos a {esc(CONTACTO)}." if CONTACTO else ""
    pie = ("<footer><h2>Cómo funciona CEV NOTICIAS</h2>"
           "Reunimos titulares de medios que revisamos y aprobamos. No copiamos las notas: cada tarjeta enlaza a la fuente original, "
           "que es la responsable de su contenido. La etiqueta Confirmado aparece cuando dos medios distintos reportan el mismo hecho. "
           f"El sitio se actualiza solo cada 30 minutos.{contacto}</footer>")
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>CEV NOTICIAS</title>'
            '<meta name="description" content="Noticias de Cali, Valle del Cauca, Colombia y el mundo, con la fuente de cada nota.">'
            f'<style>{CSS}</style></head><body><header><h1 class="marca">CEV NOTICIAS</h1>'
            f'<div class="fecha">{esc(fecha)}</div></header><nav>{nav}</nav>'
            f'<main class="wrap">{cuerpo}{pie}</main></body></html>')


def main():
    feeds = json.loads(Path("feeds.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(4) as ex:
        listas = list(ex.map(descargar, feeds))
    vistos, notas = set(), []
    for lista in listas:
        for n in lista:
            clave = (n["fuente"], n["titulo"].lower())
            if n["link"] in vistos or clave in vistos:
                continue
            vistos.update([n["link"], clave])
            n["pal"] = palabras(n["titulo"])
            notas.append(n)
    if not notas:
        raise SystemExit("No hay notas. No se publica nada nuevo y queda la versión anterior.")
    marcar_confirmadas(notas)
    ahora = datetime.now(timezone.utc)
    por_cat = {c: sorted([n for n in notas if n["cat"] == c], key=lambda n: n["fecha"], reverse=True)[:POR_CATEGORIA]
               for c in CATEGORIAS}
    visibles = [n for c in CATEGORIAS for n in por_cat[c]]
    portada = sorted(visibles, key=lambda n: (bool(n["otras"]) and ahora - n["fecha"] < timedelta(hours=12), n["fecha"]),
                     reverse=True)[:5]
    Path("site").mkdir(exist_ok=True)
    Path("site/index.html").write_text(pagina(por_cat, portada, ahora), encoding="utf-8")
    print(f"Sitio generado con {len(visibles)} notas.")


if __name__ == "__main__":
    main()
