import json
import re
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).parent
SITE = BASE / "site"
NOTAS = SITE / "notas"
CACHE = BASE / "cache.json"

SECCIONES = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología", "Economía", "Tendencias", "Humor y opinión"]
COLOMBIA_TZ = timezone(timedelta(hours=-5))


def escapar(valor):
    return html.escape(str(valor or ""), quote=True)


def cargar_json(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return defecto


def slug(texto):
    texto = str(texto).lower()
    for original, nuevo in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
        texto = texto.replace(original, nuevo)
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:75]


def fecha_actual():
    return datetime.now(COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p")


def fecha_ordenable(noticia):
    valor = str(noticia.get("fecha", "")).strip()
    for formato in ("%d/%m/%Y · %I:%M %p", "%d/%m/%Y %I:%M %p"):
        try:
            return datetime.strptime(valor, formato).timestamp()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return 0


def imagen_segura(url):
    url = str(url or "").strip()
    return escapar(url) if url.startswith(("https://", "http://")) else ""


def tarjeta(noticia, posicion=0):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    imagen = imagen_segura(noticia.get("imagen"))
    identificador = escapar(noticia.get("id"))
    visual = f'<img src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else f'<div class="portada-sin-foto"><strong>CEV</strong><span>{categoria}</span></div>'
    return f"""
    <article class="tarjeta tarjeta-vertical">
      <a class="tarjeta-enlace" href="notas/{identificador}.html">
        <div class="tarjeta-imagen">{visual}</div>
        <div class="tarjeta-contenido">
          <span class="etiqueta">{categoria}</span>
          <h3>{titulo}</h3>
          <p>{resumen}</p>
          <span class="leer">Leer noticia <span aria-hidden="true">↗</span></span>
        </div>
      </a>
    </article>"""


def tarjeta_rss(titular):
    titulo = escapar(titular.get("titulo"))
    categoria = escapar(titular.get("categoria"))
    identificador = escapar(titular.get("id"))
    imagen = imagen_segura(titular.get("imagen"))
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    visual = f'<img src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else f'<div class="portada-sin-foto"><strong>CEV</strong><span>{categoria}</span></div>'
    return f"""
    <article class="tarjeta tarjeta-vertical titular-externo">
      <a class="tarjeta-enlace titular-rss-enlace" href="notas/actualidad-{identificador}.html">
        <div class="tarjeta-imagen">{visual}</div>
        <div class="tarjeta-contenido">
          <span class="rss-sello">CEV NOTICIAS · ACTUALIDAD</span>
          <h3>{titulo}</h3>
          <div class="rss-datos"><strong>{categoria}</strong><span>{fecha_texto}</span></div>
          <span class="leer">Consultar información ↗</span>
        </div>
      </a>
    </article>"""


def tarjeta_express(item):
    titulo = escapar(item.get("titulo"))
    categoria = escapar(item.get("categoria"))
    imagen = imagen_segura(item.get("imagen"))
    identificador = escapar(item.get("id"))
    es_rss = item.get("tipo") == "rss"
    href = f"notas/actualidad-{identificador}.html" if es_rss else f"notas/{identificador}.html"
    resumen = escapar(item.get("resumen", "")) if not es_rss else "Sigue esta noticia y consulta la información completa."
    fecha = fecha_ordenable(item)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    visual = f'<img src="{imagen}" alt="" loading="lazy">' if imagen else '<div class="express-foto-vacia">CEV</div>'
    sello = "CEV NOTICIAS · EXPRESS" if not es_rss else "CEV NOTICIAS · EXPRESS"
    return f"""
    <article class="express-slide">
      <a class="express-enlace" href="{href}">
        <div class="express-foto">{visual}</div>
        <div class="express-texto">
          <span class="express-sello">{sello} · {categoria}</span>
          <h3>{titulo}</h3>
          <p>{resumen}</p>
          <span class="express-leer">Abrir noticia ↗</span>
          <small>{fecha_texto}</small>
        </div>
      </a>
    </article>"""


def modulo_express(items):
    if not items:
        return ""
    slides = "".join(
        tarjeta_express(item) if i == 0 else tarjeta_express(item).replace(
            '<article class="express-slide">', '<article class="express-slide" hidden>', 1
        )
        for i, item in enumerate(items)
    )
    total = len(items)
    return f"""
    <section class="express-modulo" aria-label="CEV Express">
      <div class="express-cabecera">
        <div><span class="express-marca">EXPRESS</span><span class="express-descripcion">Noticias que se mueven contigo</span></div>
        <span class="express-contador" id="express-contador">01 / {total:02d}</span>
      </div>
      <div class="express-escenario" id="express-escenario" aria-live="off">
        {slides}
      </div>
      <div class="express-controles">
        <span class="express-estado">ACTUALIDAD EN ROTACIÓN</span>
        <div>
          <button type="button" id="express-pausa" aria-label="Pausar rotación">Pausar</button>
          <button type="button" id="express-anterior" aria-label="Noticia anterior">←</button>
          <button type="button" id="express-siguiente" aria-label="Noticia siguiente">→</button>
        </div>
      </div>
    </section>"""


def lista_vertical(noticias, titulares, categoria=None, excluir=None):
    excluir = excluir or set()
    elementos = []
    for noticia in noticias:
        if noticia.get("id") in excluir or (categoria and noticia.get("categoria") != categoria):
            continue
        elementos.append((fecha_ordenable(noticia), tarjeta(noticia)))
    for titular in titulares:
        if categoria and titular.get("categoria") != categoria:
            continue
        if titular.get("id") in excluir:
            continue
        elementos.append((fecha_ordenable(titular), tarjeta_rss(titular)))
    elementos.sort(key=lambda elemento: elemento[0], reverse=True)
    return "".join(html_card for _, html_card in elementos)


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS", ruta_raiz="", extra_head=""):
    enlaces = "".join(
        f'<a href="{ruta_raiz}secciones/{slug(s)}.html">{escapar(s)}</a>'
        for s in SECCIONES
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f7f6f2">
<meta name="description" content="{escapar(descripcion)}">
{extra_head}
<title>{escapar(titulo)} | CEV NOTICIAS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--papel:#f7f6f2;--blanco:#fff;--tinta:#171717;--suave:#686868;--linea:#dedbd4;--rojo:#b5282f;--ancho:1280px}}
*{{box-sizing:border-box}}
[hidden]{{display:none!important}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--papel);color:var(--tinta);font-family:'DM Sans',Arial,sans-serif}}
a{{color:inherit;text-decoration:none}}
.masthead{{background:var(--papel)}}
.cabecera{{max-width:var(--ancho);margin:auto;padding:28px 28px 18px;text-align:center}}
.marca{{font-family:'Playfair Display',Georgia,serif;font-weight:800;font-size:clamp(43px,7vw,76px);line-height:.98;letter-spacing:-3.5px}}
.marca span{{color:var(--rojo)}}
.eslogan{{margin-top:10px;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#555}}
.instagram-marca{{display:inline-flex;align-items:center;justify-content:center;gap:8px;margin:14px auto 0;color:var(--tinta);font-size:11px;text-align:left}} .instagram-marca svg{{width:25px;height:25px;color:var(--rojo);flex:none}} .instagram-marca span{{display:flex;flex-direction:column;gap:2px}} .instagram-marca strong{{font-size:11px;font-weight:800}} .instagram-marca small{{font-size:10px;color:var(--suave)}} .instagram-marca:hover strong{{color:var(--rojo)}}
.cabecera-meta{{display:flex;justify-content:space-between;align-items:center;margin-top:22px;padding-top:11px;border-top:1px solid var(--tinta);font-size:11px;color:#555}}
.estado{{font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:var(--rojo)}}
nav{{border-top:1px solid var(--linea);border-bottom:1px solid var(--tinta);background:var(--papel)}}
.nav-interior{{max-width:850px;margin:0 auto;display:flex;justify-content:flex-start;gap:clamp(15px,3vw,34px);padding:14px 22px;overflow-x:auto;white-space:nowrap;scrollbar-width:none;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scroll-behavior:auto}} .nav-interior::-webkit-scrollbar{{display:none}}
nav a{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px}}
nav a:hover,nav a:focus{{color:var(--rojo)}}
.contenedor{{max-width:var(--ancho);margin:0 auto;padding:0 28px}}
.cinta{{display:flex;align-items:center;gap:12px;margin:27px 0 18px;font-size:10px;font-weight:800;letter-spacing:1.7px;text-transform:uppercase}}
.cinta:after{{content:"";height:1px;background:var(--linea);flex:1}}
.cinta-enlace{{display:inline-flex;align-items:center;gap:7px;color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1px;text-decoration:none;white-space:nowrap}} .cinta-enlace:hover{{text-decoration:underline;text-underline-offset:4px}}
.cinta span{{color:var(--rojo)}}
 .portada-grid{{display:block;padding-bottom:27px;border-bottom:1px solid var(--tinta)}}
.destacada{{min-width:0}}
.destacada-visual{{height:340px;overflow:hidden;background:#e7e3dc}}
.destacada-visual img{{width:100%;height:100%;object-fit:cover;display:block}}
.destacada-visual .imagen-vacia{{height:100%}}
.destacada-texto{{padding:18px 4px 0 0}}
.etiqueta{{display:inline-block;color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase}}
.destacada h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(34px,4vw,52px);line-height:1.04;letter-spacing:-1.5px;margin:10px 0}}
.destacada p{{font-size:14px;line-height:1.7;color:var(--suave);max-width:740px;margin:8px 0}}
.meta-noticia{{font-size:10px;color:#777;margin-top:13px;text-transform:uppercase;letter-spacing:.8px}}
.boton{{display:inline-flex;align-items:center;gap:14px;margin-top:13px;padding:10px 0;border-top:1px solid var(--tinta);border-bottom:1px solid var(--tinta);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px}}
.boton:hover{{color:var(--rojo);border-color:var(--rojo)}}
.lateral{{padding-left:25px;border-left:1px solid var(--linea)}}
.lateral-titulo{{display:flex;align-items:center;gap:9px;margin:0 0 8px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1.4px}}
.lateral-titulo:before{{content:"";width:7px;height:7px;background:var(--rojo);border-radius:50%}}
.relevante{{padding:17px 0;border-bottom:1px solid var(--linea)}}
.relevante:first-of-type{{padding-top:12px}}
.relevante .etiqueta{{font-size:9px}}
.relevante h3{{font-family:'Playfair Display',Georgia,serif;font-size:21px;line-height:1.18;margin:7px 0}}
.relevante p{{font-size:11px;line-height:1.55;color:var(--suave);margin:0}}
.relevante a:hover h3{{color:var(--rojo)}}
.bloque-categoria{{padding:30px 0 34px;border-bottom:1px solid var(--linea)}}
.titulo-seccion{{display:flex;align-items:baseline;gap:13px;margin:0 0 20px;font-family:'Playfair Display',Georgia,serif;font-size:clamp(25px,3vw,34px);letter-spacing:-.6px}}
.titulo-seccion:after{{content:"";height:1px;background:var(--linea);flex:1}}
.rejilla{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}}
.tarjeta{{min-width:0}}
.tarjeta-enlace{{display:block;height:100%}}
.tarjeta-imagen{{height:190px;overflow:hidden;background:#e7e3dc}}
.tarjeta-imagen img{{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s}}
.tarjeta:hover .tarjeta-imagen img{{transform:scale(1.035)}}
.imagen-vacia{{display:grid;place-items:center;background:linear-gradient(135deg,#e8e4dc,#d4d0c8);color:#6b6258;font-family:'Playfair Display',serif;font-size:30px;font-weight:800;letter-spacing:2px}}
.tarjeta.titular-externo{{background:var(--blanco);border:1px solid var(--linea);border-top:4px solid var(--rojo);min-height:260px;display:flex}}
.titular-rss-enlace{{display:flex;flex-direction:column;align-items:flex-start;gap:12px;width:100%;padding:19px}}
.rss-sello{{font-size:9px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:var(--rojo)}}
.tarjeta.titular-externo h3{{font-family:'Playfair Display',Georgia,serif;font-size:22px;line-height:1.2;margin:0}}
.rss-datos{{display:flex;flex-direction:column;gap:4px;margin-top:auto;color:var(--suave);font-size:10px}}
.tarjeta.titular-externo .leer{{margin-top:4px}}

/* Categorías en cuadrícula fija: sin desplazamiento automático */
.rejilla.rejilla-categorias{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;width:100%;max-width:100%;overflow:visible;padding:0;scroll-snap-type:none;touch-action:auto}}
.rejilla.rejilla-categorias .tarjeta{{flex:initial;width:auto;min-width:0}}
.bloque-categoria{{overflow:visible}}
.nav-interior{{justify-content:center;overflow-x:auto;scroll-behavior:smooth}}
.ficha-actualidad .credito-fuente{{margin-top:36px}}
.ficha-actualidad .credito-fuente .boton{{display:inline-flex;padding:12px 0}}
.nota-atribucion{{font-size:11px;color:var(--suave);line-height:1.65;margin-top:18px}}
/* CEV Express: carrusel independiente de la portada y de las secciones */
.express-modulo{{max-width:var(--ancho);margin:22px auto 12px;padding:0 28px}}
.express-cabecera,.express-controles{{display:flex;align-items:center;justify-content:space-between;gap:14px}}
.express-cabecera{{border-bottom:3px solid var(--rojo);padding:0 0 10px}}
.express-cabecera>div{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}}
.express-marca{{font-size:20px;font-weight:900;letter-spacing:2px;color:var(--rojo)}}
.express-descripcion{{font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--suave)}}
.express-contador{{font-size:10px;font-weight:800;letter-spacing:1px;color:var(--suave);font-variant-numeric:tabular-nums}}
.express-escenario{{background:var(--blanco);border-bottom:1px solid var(--linea)}}
.express-slide[hidden]{{display:none!important}}
.express-enlace{{display:grid;grid-template-columns:minmax(180px,27%) minmax(0,1fr);gap:22px;align-items:center;padding:15px 0}}
.express-foto{{height:145px;overflow:hidden;background:#dedbd4}}
.express-foto img{{width:100%;height:100%;object-fit:cover;display:block}}
.express-foto-vacia{{height:100%;display:grid;place-items:center;background:linear-gradient(135deg,#171717,#b5282f);color:white;font:800 35px 'Playfair Display',Georgia,serif}}
.express-texto{{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:7px}}
.express-sello{{font-size:9px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:var(--rojo)}}
.express-texto h3{{font:700 clamp(21px,2.5vw,30px)/1.12 'Playfair Display',Georgia,serif;margin:0}}
.express-texto p{{font-size:12px;color:var(--suave);line-height:1.5;margin:0;max-width:800px}}
.express-leer{{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo)}}
.express-texto small{{font-size:9px;color:var(--suave)}}
.express-controles{{padding:8px 0 0}}
.express-estado{{font-size:8px;font-weight:800;letter-spacing:1.2px;color:var(--suave)}}
.express-controles>div{{display:flex;gap:6px}}
.express-controles button{{background:transparent;border:1px solid var(--linea);color:var(--tinta);padding:6px 10px;font:700 10px 'DM Sans',sans-serif;cursor:pointer}}
.express-controles button:hover{{border-color:var(--rojo);color:var(--rojo)}}
body.noche .express-escenario{{background:var(--blanco)}}
body.noche .express-controles button{{color:var(--tinta)}}
@media(max-width:650px){{
 .express-modulo{{padding:0 16px;margin-top:16px}}
 .express-marca{{font-size:17px}}
 .express-descripcion{{font-size:8px}}
 .express-enlace{{grid-template-columns:112px minmax(0,1fr);gap:13px}}
 .express-foto{{height:118px}}
 .express-texto h3{{font-size:19px;line-height:1.15}}
 .express-texto p{{font-size:10px;display:none}}
 .express-sello{{font-size:8px;letter-spacing:.6px}}
 .express-estado{{font-size:7px}}
}}

/* Portada y secciones con lectura vertical, inspirada en diarios digitales */
.lista-noticias{{display:flex;flex-direction:column;border-top:1px solid var(--linea)}}
.tarjeta-vertical{{display:block;border-bottom:1px solid var(--linea);padding:22px 0}}
.tarjeta-vertical .tarjeta-enlace{{display:grid;grid-template-columns:minmax(220px,34%) minmax(0,1fr);gap:25px;align-items:center}}
.tarjeta-vertical .tarjeta-imagen{{height:205px;min-height:0;aspect-ratio:16/10}}
.tarjeta-vertical .tarjeta-imagen img{{width:100%;height:100%;object-fit:cover}}
.tarjeta-vertical .tarjeta-contenido{{padding:0}}
.tarjeta-vertical h3{{font-size:clamp(22px,2.5vw,31px);line-height:1.14;margin:9px 0}}
.tarjeta-vertical p{{font-size:13px;line-height:1.7;max-width:760px;margin:8px 0 14px}}
.tarjeta-vertical .leer{{display:inline-block;margin-top:5px}}
.tarjeta-vertical.titular-externo{{display:block;min-height:0;background:transparent;border:0;border-bottom:1px solid var(--linea)}}
.tarjeta-vertical.titular-externo h3{{font-family:'Playfair Display',Georgia,serif}}
.tarjeta-vertical .titular-rss-enlace{{padding:0;gap:0}}
.portada-sin-foto{{height:100%;min-height:150px;display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-end;gap:8px;padding:20px;background:linear-gradient(135deg,#171717 0%,#343434 60%,#b5282f 160%);color:#fff}}
.portada-sin-foto strong{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(30px,4vw,48px);letter-spacing:-2px}}
.portada-sin-foto span{{font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#f2d4d4}}
.portada-ficha{{max-width:740px;height:360px;margin:25px auto}}
.pagina-seccion{{padding-top:30px;padding-bottom:50px}}
.cabecera-seccion{{padding:5px 0 25px;border-bottom:1px solid var(--tinta);margin-bottom:8px}}
.cabecera-seccion h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(42px,7vw,74px);line-height:1;margin:10px 0}}
.cabecera-seccion p:last-child{{color:var(--suave);font-size:14px;line-height:1.6}}
@media(max-width:650px){{.tarjeta-vertical{{padding:18px 0}}.tarjeta-vertical .tarjeta-enlace{{grid-template-columns:1fr;gap:12px}}.tarjeta-vertical .tarjeta-imagen{{height:auto;aspect-ratio:16/9}}.tarjeta-vertical h3{{font-size:24px}}.portada-ficha{{height:240px}}}}

@media(max-width:900px){{.rejilla.rejilla-categorias{{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}}}
@media(max-width:650px){{.rejilla.rejilla-categorias{{display:grid;grid-template-columns:1fr;gap:20px;overflow:visible}}.rejilla.rejilla-categorias .tarjeta{{width:auto;flex:none}}.nav-interior{{justify-content:flex-start}}}}

.tarjeta-contenido{{padding:13px 0 4px}}
.tarjeta h3{{font-family:'Playfair Display',Georgia,serif;font-size:22px;line-height:1.16;letter-spacing:-.4px;margin:8px 0}}
.tarjeta p{{font-size:12px;line-height:1.65;color:var(--suave);margin:8px 0 12px}}
.leer{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo)}}
.vacio{{padding:20px 0;color:var(--suave);font-size:13px;border-top:1px solid var(--linea)}}
.articulo{{max-width:900px;margin:36px auto 65px;padding:0 28px}}
.articulo-cabecera{{max-width:780px;margin:0 auto 25px}}
.volver{{display:inline-block;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo);margin-bottom:30px}}
.articulo h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(38px,6vw,66px);line-height:1.03;letter-spacing:-1.8px;margin:13px 0 18px}}
.articulo .bajada{{font-size:clamp(17px,2vw,21px);line-height:1.6;color:#555;margin:0}}
.articulo .fecha{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#777;margin:22px 0}}
.articulo .foto{{width:100%;max-height:560px;object-fit:cover;display:block;margin:25px 0 8px}}
.credito-imagen{{max-width:740px;margin:0 auto 30px;font-size:11px;line-height:1.6;color:#777}}
.credito-imagen a{{text-decoration:underline}}
.articulo .cuerpo{{max-width:740px;margin:auto;font-family:Georgia,serif;font-size:19px;line-height:1.9;color:#292929;white-space:pre-line}}
.articulo .cuerpo p{{margin:0 0 24px}}
.fuentes{{max-width:740px;margin:42px auto 0;padding-top:20px;border-top:1px solid var(--linea);font-size:12px;color:#666}}
.fuentes strong{{color:var(--tinta);text-transform:uppercase;letter-spacing:1px;font-size:10px}}
.fuentes li{{margin:8px 0}}
.pie{{margin-top:35px;background:#171717;color:#fff;padding:36px 22px;text-align:center}}
.pie strong{{font-family:'Playfair Display',Georgia,serif;font-size:30px;letter-spacing:-1px}}
.pie strong span{{color:#e14a50}}
.pie p{{color:#aaa;font-size:11px;line-height:1.7}}
/* Herramientas de lectura y navegación */
.relacionadas{{margin:48px auto 0;max-width:740px}}
.relacionadas .rejilla{{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
.relacionadas .tarjeta{{padding:16px;border:1px solid var(--linea);background:var(--blanco)}}
.relacionadas .tarjeta h3{{font-size:19px}}
.barra-herramientas{{max-width:var(--ancho);margin:auto;padding:12px 28px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--linea)}}
.buscador{{flex:1;min-width:0;padding:11px 14px;border:1px solid var(--linea);background:var(--blanco);color:var(--tinta);font:inherit;font-size:13px;border-radius:2px}}
.accion-ui{{border:1px solid var(--tinta);background:transparent;color:var(--tinta);padding:10px 13px;font:700 10px 'DM Sans',sans-serif;letter-spacing:.7px;text-transform:uppercase;cursor:pointer}}
.accion-ui:hover{{background:var(--tinta);color:var(--papel)}}
.progreso-lectura{{position:fixed;z-index:30;top:0;left:0;height:3px;width:0;background:var(--rojo)}}
.volver-arriba{{position:fixed;z-index:20;right:18px;bottom:18px;width:42px;height:42px;border:0;border-radius:50%;background:var(--rojo);color:#fff;font-size:20px;cursor:pointer;box-shadow:0 3px 14px #0003}}
body.noche{{--papel:#151515;--blanco:#222;--tinta:#fff;--suave:#d0ccc4;--linea:#484848}}
body.noche .imagen-vacia{{background:linear-gradient(135deg,#303030,#242424);color:#f5f5f5}}
body.noche .destacada-visual,body.noche .tarjeta-imagen{{background:#292929}}
body.noche .pie{{background:#090909}}
body.noche .eslogan,body.noche .cabecera-meta,body.noche .articulo .bajada,body.noche .articulo .fecha,body.noche .credito-imagen,body.noche .fuentes,body.noche .meta-noticia{{color:#d0ccc4}}
body.noche .articulo .cuerpo{{color:#f1eee8}}
body.noche .relevante p,body.noche .tarjeta p{{color:#d0ccc4}}
body.noche .accion-ui{{border-color:#aaa;color:#fff}}
body.noche .accion-ui:hover{{background:#fff;color:#151515}}
body.noche .buscador{{background:#242424;color:#fff;border-color:#555}}
body.noche .buscador::placeholder{{color:#c5c1ba}}
body.noche .volver{{color:#ff777d}}
body.noche .leer,body.noche .etiqueta{{color:#ff777d}}
body.noche .cinta-enlace{{color:#ff858a}}
body.noche .boton{{border-color:#ddd}}
body.noche .boton:hover{{color:#ff858a;border-color:#ff858a}}
body.noche .relacionadas .tarjeta{{background:#222;border-color:#484848}}
@media(max-width:650px){{
 .barra-herramientas{{padding:10px 15px;flex-wrap:wrap}}
 .buscador{{flex-basis:100%}}
 .rejilla:not(.rejilla-categorias){{display:flex;overflow-x:auto;scroll-snap-type:none;gap:14px;padding-bottom:12px;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}}
 .rejilla:not(.rejilla-categorias) .tarjeta{{flex:0 0 84%;scroll-snap-align:none}}
 .rejilla .tarjeta-imagen{{height:190px}}
}}


@media(max-width:900px){{
 .portada-grid{{grid-template-columns:minmax(0,1fr) 270px;gap:22px}}
 .destacada-visual{{height:290px}}
 .lateral{{padding-left:18px}}
 .rejilla{{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}
}}
@media(max-width:650px){{
 .cabecera{{padding:22px 15px 15px}}
 .marca{{font-size:49px;letter-spacing:-2.5px}}
 .cabecera-meta{{font-size:9px}}
 .nav-interior{{justify-content:flex-start;padding:13px 15px}}
 .contenedor{{padding:0 16px}}
 .portada-grid{{grid-template-columns:1fr;gap:20px}}
 .destacada-visual{{height:225px}}
 .destacada h1{{font-size:36px}}
 .lateral{{border-left:0;border-top:1px solid var(--linea);padding:18px 0 0}}
 .relevante{{padding:13px 0}}
 .rejilla{{grid-template-columns:1fr;gap:22px}}
 .tarjeta-imagen{{height:210px}}
 .articulo{{padding:0 18px;margin-top:25px}}
 .articulo h1{{font-size:41px}}
 .articulo .cuerpo{{font-size:18px}}
}}
</style>
</head>
<body>
<header class="masthead">
 <div class="cabecera">
  <div class="marca"><a href="{ruta_raiz}" aria-label="CEV NOTICIAS, ir al inicio">CEV <span>NOTICIAS</span></a></div>
  <div class="eslogan">Periodismo · Contexto · Actualidad</div>
  <a class="instagram-marca" href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer" aria-label="Instagram de Cali en Vivo Noticias: @cev.noticias"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.5" cy="6.8" r="1.1" fill="currentColor"/></svg><span><strong>Cali en Vivo Noticias</strong><small>@cev.noticias</small></span></a>
  <div class="cabecera-meta"><span>{fecha_actual()} · COLOMBIA</span><span class="estado">Edición digital</span></div>
 </div>
 <nav aria-label="Secciones"><div class="nav-interior">
  <a href="{ruta_raiz}">Portada</a>{enlaces}
 </div></nav>
 <div class="barra-herramientas">
  <input id="buscar-noticias" class="buscador" type="search" placeholder="Buscar noticias, temas o palabras..." aria-label="Buscar noticias">
  <button id="modo-noche" class="accion-ui" type="button" aria-pressed="false">◐ Modo oscuro</button>
 </div>
</header>
{contenido}
<footer class="pie">
 <strong>CEV <span>NOTICIAS</span></strong>
 <p>Información, contexto y actualidad.</p>
 <p><a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Instagram · @cev.noticias</a></p>
 <p>Las fuentes consultadas se identifican al final de cada artículo.</p>
</footer>

<div class="progreso-lectura" id="progreso-lectura"></div>
<button class="volver-arriba" id="volver-arriba" type="button" aria-label="Volver arriba" title="Volver arriba">↑</button>
<script>
(function(){{
 const buscar=document.getElementById('buscar-noticias');
 if(buscar){{buscar.addEventListener('input',function(){{
  const q=this.value.trim().toLocaleLowerCase('es');
  document.querySelectorAll('.tarjeta,.relevante,.destacada').forEach(el=>{{el.hidden=!!q&&!el.innerText.toLocaleLowerCase('es').includes(q)}});
  document.querySelectorAll('.bloque-categoria').forEach(sec=>{{sec.hidden=!!q&&sec.querySelectorAll('.tarjeta:not([hidden])').length===0}});
 }});}}
 const modo=document.getElementById('modo-noche');
 if(modo){{modo.addEventListener('click',()=>{{
  const activo=document.body.classList.toggle('noche');
  modo.setAttribute('aria-pressed',String(activo));modo.textContent=activo?'☀ Modo claro':'◐ Modo oscuro';
  try{{localStorage.setItem('cev-modo',activo?'noche':'claro')}}catch(e){{}}
 }});
 try{{if(localStorage.getItem('cev-modo')==='noche'){{document.body.classList.add('noche');modo.textContent='☀ Modo claro';modo.setAttribute('aria-pressed','true')}}}}catch(e){{}}}}
 const express=document.querySelectorAll('.express-slide');
 if(express.length){{
  let indice=0,temporizador=null,pausado=false;
  const contador=document.getElementById('express-contador');
  const pausa=document.getElementById('express-pausa');
  const escenario=document.getElementById('express-escenario');
  function mostrarExpress(n){{
   express[indice].hidden=true;
   indice=(n+express.length)%express.length;
   express[indice].hidden=false;
   if(contador)contador.textContent=String(indice+1).padStart(2,'0')+' / '+String(express.length).padStart(2,'0');
  }}
  function detenerExpress(){{if(temporizador)clearInterval(temporizador);temporizador=null;}}
  function iniciarExpress(){{detenerExpress();if(!pausado&&express.length>1&&!document.hidden)temporizador=setInterval(()=>mostrarExpress(indice+1),6500);}}
  function cambiarPausa(){{pausado=!pausado;if(pausa){{pausa.textContent=pausado?'Reanudar':'Pausar';pausa.setAttribute('aria-label',pausado?'Reanudar rotación':'Pausar rotación');}}iniciarExpress();}}
  document.getElementById('express-siguiente')?.addEventListener('click',()=>{{mostrarExpress(indice+1);iniciarExpress();}});
  document.getElementById('express-anterior')?.addEventListener('click',()=>{{mostrarExpress(indice-1);iniciarExpress();}});
  pausa?.addEventListener('click',cambiarPausa);
  escenario?.addEventListener('mouseenter',detenerExpress);
  escenario?.addEventListener('mouseleave',iniciarExpress);
  escenario?.addEventListener('focusin',detenerExpress);
  escenario?.addEventListener('focusout',iniciarExpress);
  document.addEventListener('visibilitychange',iniciarExpress);
  iniciarExpress();
 }}
 const barra=document.getElementById('progreso-lectura'),arriba=document.getElementById('volver-arriba');
 function actualizar(){{const max=document.documentElement.scrollHeight-window.innerHeight;if(barra)barra.style.width=(max>0?(window.scrollY/max)*100:0)+'%';if(arriba)arriba.hidden=window.scrollY<450;}}
 window.addEventListener('scroll',actualizar,{{passive:true}});actualizar();
 if(arriba)arriba.addEventListener('click',()=>window.scrollTo({{top:0,behavior:'smooth'}}));
}})();
</script>
</body>
</html>"""


def crear_articulo(noticia, noticias=None):
    identificador = noticia["id"]
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    contenido = str(noticia.get("contenido") or "").strip()
    imagen = imagen_segura(noticia.get("imagen"))
    foto = f'<img class="foto" src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else f'<div class="portada-sin-foto portada-ficha"><strong>CEV NOTICIAS</strong><span>{categoria}</span></div>'
    credito = noticia.get("imagen_credito") or {}
    atribucion_imagen = ""
    if imagen and credito:
        autor = escapar(credito.get("autor", "Autor no identificado"))
        origen = escapar(credito.get("fuente", "Archivo de imágenes"))
        licencia = escapar(credito.get("licencia", "Consultar licencia"))
        pagina_imagen = imagen_segura(credito.get("pagina", ""))
        licencia_url = imagen_segura(credito.get("licencia_url", ""))
        enlaces_credito = []
        if pagina_imagen:
            enlaces_credito.append(f'<a href="{pagina_imagen}" target="_blank" rel="noopener">fuente original</a>')
        if licencia_url:
            enlaces_credito.append(f'<a href="{licencia_url}" target="_blank" rel="noopener">licencia</a>')
        extras = " · ".join(enlaces_credito)
        atribucion_imagen = f'<p class="credito-imagen">Imagen: {autor} · {origen} · {licencia} {extras}</p>'
    parrafos = "".join(f"<p>{escapar(p.strip())}</p>" for p in contenido.split("\n\n") if p.strip())
    noticias = noticias or [noticia]
    def palabras(texto):
        return set(re.findall(r"[a-záéíóúñü]{4,}", str(texto or "").lower()))
    actuales = palabras(noticia.get("titulo", "") + " " + noticia.get("resumen", ""))
    relacionadas = []
    for otra in noticias:
        if otra.get("id") == identificador:
            continue
        comunes = len(actuales & palabras(otra.get("titulo", "") + " " + otra.get("resumen", "")))
        puntaje = comunes + (2 if otra.get("categoria") == noticia.get("categoria") else 0)
        if puntaje:
            relacionadas.append((puntaje, otra))
    relacionadas.sort(key=lambda x: x[0], reverse=True)
    bloque_relacionadas = ""
    if relacionadas:
        tarjetas_rel = "".join(
            f'<article class="tarjeta"><a class="tarjeta-enlace" href="{html.escape(otra.get("id", ""), quote=True)}.html"><span class="etiqueta">{escapar(otra.get("categoria"))}</span><h3>{escapar(otra.get("titulo"))}</h3><p>{escapar(otra.get("resumen"))}</p><span class="leer">Leer noticia ↗</span></a></article>'
            for _, otra in relacionadas[:3]
        )
        bloque_relacionadas = f'<section class="relacionadas"><h2 class="titulo-seccion">También te puede interesar</h2><div class="rejilla">{tarjetas_rel}</div></section>'
    referencias = []
    for fuente in noticia.get("fuentes", []):
        nombre_fuente = escapar(fuente.get("nombre", "Fuente consultada"))
        titulo_fuente = escapar(fuente.get("titulo") or fuente.get("nombre", "Fuente consultada"))
        url_fuente = imagen_segura(fuente.get("url", ""))
        texto_fuente = f'<a href="{url_fuente}" target="_blank" rel="noopener noreferrer">{titulo_fuente}</a>' if url_fuente else titulo_fuente
        referencias.append(f"<li>{texto_fuente} · {nombre_fuente}</li>")
    cuerpo = f"""
    <main class="articulo">
      <div class="articulo-cabecera">
       <a class="volver" href="../index.html">← Volver a la portada</a>
       <p class="etiqueta">{categoria}</p>
       <h1>{titulo}</h1>
       <p class="bajada">{resumen}</p>
       <p class="fecha">Publicado: {escapar(noticia.get("fecha", fecha_actual()))} · Por CEV NOTICIAS</p>
       <p class="fecha">Verificación editorial: {escapar(noticia.get("verificacion", "Fuente consultada; ver referencias"))}</p>
      </div>
      {foto}
      {atribucion_imagen}
      <div class="cuerpo">{parrafos}</div>
      <div class="fuentes"><strong>Fuentes consultadas</strong><ul>{''.join(referencias)}</ul>
       <p>Artículo de elaboración propia. Las fuentes se presentan para consulta y contraste.</p>
      </div>
      {bloque_relacionadas}
    </main>"""
    url_articulo = f"https://cevnoticias.com/notas/{identificador}.html"
    datos_schema = {"@context":"https://schema.org","@type":"NewsArticle","headline":str(noticia.get("titulo","")),"description":str(noticia.get("resumen","")),"author":{"@type":"Organization","name":"CEV NOTICIAS"},"publisher":{"@type":"Organization","name":"CEV NOTICIAS"},"mainEntityOfPage":url_articulo}
    if imagen:
        datos_schema["image"] = imagen
    extra_head = f'<link rel="canonical" href="{url_articulo}"><meta property="og:type" content="article"><meta property="og:title" content="{titulo}"><meta property="og:description" content="{resumen}"><meta property="og:url" content="{url_articulo}">' + (f'<meta property="og:image" content="{imagen}">' if imagen else "") + '<script type="application/ld+json">' + json.dumps(datos_schema, ensure_ascii=False) + '</script>'
    pagina = plantilla(titulo, cuerpo, resumen, ruta_raiz="../", extra_head=extra_head)
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"{identificador}.html").write_text(pagina, encoding="utf-8")


def crear_pagina_titular_rss(titular):
    identificador = escapar(titular.get("id"))
    titulo = escapar(titular.get("titulo"))
    categoria = escapar(titular.get("categoria"))
    fuente = escapar(titular.get("fuente", "Medio de origen"))
    url_original = imagen_segura(titular.get("url"))
    imagen = imagen_segura(titular.get("imagen"))
    foto = f'<img class="foto" src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else f'<div class="portada-sin-foto portada-ficha"><strong>CEV NOTICIAS</strong><span>{categoria}</span></div>'
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p") if fecha else "Fecha no disponible"

    cuerpo = f"""
    <main class="articulo ficha-actualidad">
      <div class="articulo-cabecera">
        <a class="volver" href="../index.html">← Volver a CEV NOTICIAS</a>
        <p class="etiqueta">{categoria}</p>
        <p class="fecha">Titular recopilado por CEV NOTICIAS · No es un artículo original de nuestra redacción</p>
        <h1>{titulo}</h1>
        <p class="bajada">Este titular forma parte del seguimiento de actualidad de CEV NOTICIAS. Para consultar el desarrollo completo, los datos y el contexto de la información, visita la publicación original.</p>
        <p class="fecha">Publicado originalmente: {fecha_texto}</p>
      </div>
      {foto}
      <section class="fuentes credito-fuente">
        <strong>Crédito de información</strong>
        <p>La publicación original y su desarrollo periodístico corresponden a <strong>{fuente}</strong>.</p>
        <p><a class="boton" href="{url_original}" target="_blank" rel="noopener noreferrer">Consultar la noticia en {fuente} ↗</a></p>
        <p class="nota-atribucion">CEV NOTICIAS identifica el medio de origen y enlaza a su cobertura. El contenido completo pertenece a la publicación citada.</p>
      </section>
    </main>"""

    extra_head = '<meta name="robots" content="noindex,follow">'
    pagina = plantilla(
        titulo,
        cuerpo,
        "Titular de actualidad recopilado por CEV NOTICIAS con crédito al medio original.",
        ruta_raiz="../",
        extra_head=extra_head
    )
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"actualidad-{identificador}.html").write_text(pagina, encoding="utf-8")



def crear_pagina_seccion(seccion, noticias, titulares):
    nombre = escapar(seccion)
    slug_seccion = slug(seccion)
    tarjetas = lista_vertical(noticias, titulares, categoria=seccion)
    listado = tarjetas or '<div class="vacio">No hay noticias disponibles en esta sección por ahora.</div>'
    cuerpo = f"""
    <main class="contenedor pagina-seccion">
      <a class="volver" href="../index.html">← Volver a la portada</a>
      <header class="cabecera-seccion">
        <p class="etiqueta">CEV NOTICIAS · SECCIÓN</p>
        <h1>{nombre}</h1>
        <p>Las noticias más recientes de {nombre}, organizadas en orden de publicación.</p>
      </header>
      <section class="lista-noticias" aria-label="Noticias de {nombre}">
        {listado}
      </section>
    </main>"""
    pagina = plantilla(
        seccion,
        cuerpo,
        f"Noticias de {seccion} en CEV NOTICIAS.",
        ruta_raiz="../"
    )
    carpeta = SITE / "secciones"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{slug_seccion}.html").write_text(pagina, encoding="utf-8")


def construir():
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])
    titulares_rss = datos.get("titulares_rss", []) if isinstance(datos.get("titulares_rss", []), list) else []
    validas = []
    vistos = set()
    titulos_vistos = set()
    for noticia in noticias:
        titulo = str(noticia.get("titulo", "")).strip()
        contenido = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")
        if not titulo or len(contenido) < 250 or categoria not in SECCIONES:
            continue
        identificador = noticia.get("id") or slug(titulo)
        titulo_normalizado = re.sub(r"[^a-z0-9]+", " ", titulo.lower()).strip()
        if identificador in vistos or titulo_normalizado in titulos_vistos:
            continue
        noticia["id"] = identificador
        noticia.setdefault("fecha", fecha_actual())
        noticia.setdefault("resumen", contenido[:220])
        noticia.setdefault("fuentes", [])
        vistos.add(identificador)
        titulos_vistos.add(titulo_normalizado)
        validas.append(noticia)
    
    validas.sort(key=fecha_ordenable, reverse=True)

    for noticia in validas:
        crear_articulo(noticia, validas)

    SITE.mkdir(parents=True, exist_ok=True)
    # Los RSS se conservan solo como material de investigación interno; no se publican como noticias.
    principal = validas[0] if validas else None
    laterales = validas[1:4]
    if principal:
        imagen = imagen_segura(principal.get("imagen"))
        visual = f'<img src="{imagen}" alt="{escapar(principal.get("titulo"))}" fetchpriority="high">' if imagen else '<div class="imagen-vacia">CEV</div>'
        principal_html = f"""
        <article class="destacada">
         <a href="notas/{escapar(principal['id'])}.html">
          <div class="destacada-visual">{visual}</div>
          <div class="destacada-texto">
           <span class="etiqueta">Noticia central · {escapar(principal['categoria'])}</span>
           <h1>{escapar(principal['titulo'])}</h1>
           <p>{escapar(principal['resumen'])}</p>
           <div class="meta-noticia">{escapar(principal.get('fecha', fecha_actual()))}</div>
           <span class="boton">Leer noticia completa <span>↗</span></span>
          </div>
         </a>
        </article>"""
    else:
        principal_html = '<div class="vacio">Estamos preparando las próximas noticias. Vuelve pronto.</div>'

    if laterales:
        lateral_html = '<aside class="lateral"><h2 class="lateral-titulo">Las más relevantes</h2>'
        for noticia in laterales:
            lateral_html += f"""
            <article class="relevante">
             <a href="notas/{escapar(noticia['id'])}.html">
              <span class="etiqueta">{escapar(noticia['categoria'])}</span>
              <h3>{escapar(noticia['titulo'])}</h3>
              <p>{escapar(noticia.get('resumen'))}</p>
             </a>
            </article>"""
        lateral_html += "</aside>"
    else:
        lateral_html = '<aside class="lateral"><h2 class="lateral-titulo">Las más relevantes</h2><p class="vacio">Próximamente encontrarás aquí más noticias destacadas.</p></aside>'

    portada = f'<section class="portada-grid">{principal_html}</section>'

    # Cada sección cuenta con una página propia; la portada mantiene un único flujo vertical.
    for seccion in SECCIONES:
        crear_pagina_seccion(seccion, validas, [])

    candidatos_express = []
    for noticia in validas:
        if principal and noticia["id"] == principal["id"]:
            continue
        item = dict(noticia)
        item["tipo"] = "propia"
        candidatos_express.append(item)
    candidatos_express.sort(key=fecha_ordenable, reverse=True)
    noticias_express = candidatos_express[:5]
    ids_express = {item["id"] for item in noticias_express}

    express_html = modulo_express(noticias_express)
    lista_portada = lista_vertical(
        validas,
        [],
        excluir=ids_express | ({principal["id"]} if principal else set())
    )
    contenido = (
        f'{express_html}'
        '<main class="contenedor">'
        '<div class="cinta"><span>En desarrollo</span><span>Últimas noticias</span></div>'
        f'{portada}'
        '<section class="bloque-categoria" id="ultimas-noticias">'
        '<h2 class="titulo-seccion">Últimas noticias</h2>'
        f'<div class="lista-noticias">{lista_portada or "<div class=vacio>No hay noticias disponibles por ahora.</div>"}</div>'
        '</section></main>'
    )
    portada_head = '<link rel="canonical" href="https://cevnoticias.com/"><meta property="og:type" content="website"><meta property="og:title" content="CEV NOTICIAS | Actualidad y periodismo">'
    (SITE / "index.html").write_text(plantilla("Portada", contenido, "Noticias de Cali, Valle del Cauca, Colombia y el mundo.", extra_head=portada_head), encoding="utf-8")
    urls = ["https://cevnoticias.com/"] + [f"https://cevnoticias.com/notas/{n['id']}.html" for n in validas] + [f"https://cevnoticias.com/secciones/{slug(s)}.html" for s in SECCIONES]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\\n' + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\\n' + ''.join(f'<url><loc>{html.escape(url)}</loc></url>\\n' for url in urls) + '</urlset>\\n'
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (SITE / "robots.txt").write_text("User-agent: *\\nAllow: /\\nSitemap: https://cevnoticias.com/sitemap.xml\\n", encoding="utf-8")
    print(f"Portada creada. Artículos propios: {len(validas)} · Titulares de fuentes: {len(titulares_rss)}")


if __name__ == "__main__":
    construir()
