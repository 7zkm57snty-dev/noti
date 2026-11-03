import json
import re
import html
from html.parser import HTMLParser
import mimetypes
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, unquote
import xml.etree.ElementTree as ET

BASE = Path(__file__).parent
SITE = BASE / "site"
NOTAS = SITE / "notas"
CACHE = BASE / "cache.json"
RADAR_RSS = BASE / "radar_rss.json"
MAX_TITULARES_PUBLICOS = 24
MAX_EDAD_TITULARES_PUBLICOS_HORAS = 72

SECCIONES = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología", "Economía", "Tendencias", "Humor y opinión"]
COLOMBIA_TZ = timezone(timedelta(hours=-5))
IMAGENES_PROCESADAS = {}


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



def fecha_schema(noticia):
    """Convierte la fecha editorial a ISO 8601 con la zona horaria de Colombia."""
    valor = str(noticia.get("fecha", "")).strip()
    for formato in ("%d/%m/%Y · %I:%M %p", "%d/%m/%Y %I:%M %p"):
        try:
            return datetime.strptime(valor, formato).replace(tzinfo=COLOMBIA_TZ).isoformat()
        except ValueError:
            pass
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=COLOMBIA_TZ)
        return fecha.isoformat()
    except (ValueError, OverflowError):
        return ""



def imagen_segura(url):
    url = str(url or "").strip()
    return escapar(url) if url.startswith(("https://", "http://")) else ""


def foto_local_noticia(noticia):
    """
    Descarga una fotografía editorial con URL válida al artefacto estático.
    Nunca usa la portada social con texto como si fuera una fotografía.
    """
    identificador = slug(noticia.get("id") or noticia.get("titulo") or "noticia")
    if identificador in IMAGENES_PROCESADAS:
        return IMAGENES_PROCESADAS[identificador]

    url = str(noticia.get("imagen") or "").strip()
    if not url.startswith(("https://", "http://")):
        IMAGENES_PROCESADAS[identificador] = ""
        return ""

    host = (urlsplit(url).hostname or "").lower()
    if host in ("cevnoticias.com", "www.cevnoticias.com"):
        IMAGENES_PROCESADAS[identificador] = ""
        return ""

    tipos = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif"
    }
    try:
        solicitud = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CEVNoticias/1.0; https://cevnoticias.com/)",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            }
        )
        with urlopen(solicitud, timeout=18) as respuesta:
            tipo = respuesta.headers.get_content_type().lower()
            extension = tipos.get(tipo)
            datos = respuesta.read(15 * 1024 * 1024 + 1)

        if not extension or len(datos) < 2048 or len(datos) > 15 * 1024 * 1024:
            raise ValueError(f"Respuesta de imagen no válida: {tipo}, {len(datos)} bytes")

        carpeta = SITE / "imagenes"
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"{identificador}{extension}"
        (carpeta / nombre).write_bytes(datos)
        local = f"/imagenes/{nombre}"
        IMAGENES_PROCESADAS[identificador] = local
        print(f"Fotografía real guardada en el sitio: {identificador}{extension}")
        return local
    except Exception as error:
        print(f"Sin foto descargable para {identificador}; la noticia se mostrará sin imagen: {error}")
        IMAGENES_PROCESADAS[identificador] = ""
        return ""


def imagen_noticia(noticia, alt="", clase="", loading="lazy", prioridad=False):
    """
    Inserta únicamente una fotografía guardada en el propio sitio.
    Si no hay fotografía real, devuelve vacío para no inventar un cartel.
    """
    fotografia = foto_local_noticia(noticia)
    if not fotografia:
        return ""

    clases = f' class="{escapar(clase)}"' if clase else ""
    prioridad_html = ' fetchpriority="high"' if prioridad else ""
    return (
        f'<img{clases} src="{fotografia}" alt="{escapar(alt)}" '
        f'loading="{escapar(loading)}" decoding="async"{prioridad_html}>'
    )


def tarjeta(noticia, posicion=0, ruta_raiz=""):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    identificador = escapar(noticia.get("id"))
    visual = imagen_noticia(noticia, alt=titulo)
    clase_sin_imagen = "" if visual else " tarjeta-sin-imagen"
    bloque_imagen = f'<div class="tarjeta-imagen">{visual}</div>' if visual else ""
    return f"""
    <article class="tarjeta tarjeta-vertical{clase_sin_imagen}">
      <a class="tarjeta-enlace" href="/notas/{identificador}.html">
        {bloque_imagen}
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
    fuente = escapar(titular.get("fuente") or "Medio externo")
    url = imagen_segura(titular.get("url"))
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    if not titulo or not url:
        return ""
    return f"""
    <article class="tarjeta tarjeta-vertical titular-externo">
      <a class="tarjeta-enlace titular-rss-enlace" href="{url}" target="_blank" rel="noopener noreferrer">
        <div class="tarjeta-contenido">
          <span class="rss-sello">OTROS MEDIOS · {fuente}</span>
          <h3>{titulo}</h3>
          <div class="rss-datos"><span>Publicado originalmente · {fecha_texto}</span></div>
          <span class="leer">Leer en {fuente} ↗</span>
        </div>
      </a>
    </article>"""


def tarjeta_express(item):
    titulo = escapar(item.get("titulo"))
    categoria = escapar(item.get("categoria"))
    identificador = escapar(item.get("id"))
    es_rss = item.get("tipo") == "rss"
    href = f"notas/actualidad-{identificador}.html" if es_rss else f"notas/{identificador}.html"
    resumen = escapar(item.get("resumen", "")) if not es_rss else "Sigue esta noticia y consulta la información completa."
    fecha = fecha_ordenable(item)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    visual = imagen_noticia(item, alt="")
    clase_sin_imagen = "" if visual else " sin-imagen"
    bloque_imagen = f'<div class="express-foto">{visual}</div>' if visual else ""
    sello = "CEV NOTICIAS · EXPRESS"
    destino = f"/notas/{identificador}.html" if not es_rss else f"/notas/actualidad-{identificador}.html"
    return f"""
    <article class="express-slide">
      <a class="express-enlace{clase_sin_imagen}" href="{destino}">
        {bloque_imagen}
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


def palabras_titulo(texto):
    ignorar = {
        "para", "desde", "sobre", "entre", "tras", "cuando", "donde",
        "porque", "como", "esta", "este", "estos", "estas", "tambien",
        "contra", "despues", "antes", "hacia", "hasta", "ante", "sera",
        "fue", "son", "los", "las", "una", "uno", "del", "por", "con",
        "sin", "que", "sus", "mas", "hoy", "ayer", "nuevo", "nueva",
        "colombia", "cali", "valle", "cauca", "noticia", "noticias"
    }
    return {
        palabra for palabra in re.findall(r"[a-záéíóúñü]{4,}", str(texto or "").lower())
        if palabra not in ignorar
    }


def titular_repite_articulo(titular, noticias):
    palabras = palabras_titulo(titular)
    if not palabras:
        return False
    for noticia in noticias:
        otras = palabras_titulo(noticia.get("titulo", ""))
        comunes = palabras.intersection(otras)
        union = palabras.union(otras)
        if len(comunes) >= 2 and len(comunes) / max(1, len(union)) >= 0.20:
            return True
    return False


def seleccionar_titulares_publicos(titulares, noticias, limite=MAX_TITULARES_PUBLICOS):
    ahora = datetime.now(timezone.utc).timestamp()
    limite = ahora - MAX_EDAD_TITULARES_PUBLICOS_HORAS * 3600
    resultado = []
    vistos = set()
    for original in titulares if isinstance(titulares, list) else []:
        if not isinstance(original, dict):
            continue
        titular = dict(original)
        titulo = str(titular.get("titulo") or "").strip()
        fuente = str(titular.get("fuente") or "").strip()
        url = str(titular.get("url") or "").strip()
        fecha = fecha_ordenable(titular)
        if not titulo or not fuente or not url.startswith("https://"):
            continue
        if not fecha or fecha < limite or fecha > ahora + 2 * 3600:
            continue
        if titular.get("categoria") not in SECCIONES:
            continue
        if titular_repite_articulo(titulo, noticias):
            continue
        clave = re.sub(r"[^a-z0-9]+", " ", titulo.lower()).strip()
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(titular)
    resultado.sort(key=fecha_ordenable, reverse=True)
    return resultado[:limite] if limite else resultado


def crear_pagina_actualidad_externa(titulares):
    tarjetas = lista_vertical([], titulares)
    contenido = f"""
    <main class="contenedor pagina-seccion">
      <a class="volver" href="/">← Volver a la portada</a>
      <header class="cabecera-seccion">
        <p class="etiqueta">CEV NOTICIAS · SEGUIMIENTO DE MEDIOS</p>
        <h1>Más actualidad</h1>
        <p>Selección de titulares recientes publicados por medios externos. Cada tarjeta identifica su fuente y enlaza directamente al contenido original. Estos titulares no son artículos propios de CEV NOTICIAS.</p>
      </header>
      <section class="rejilla rejilla-categorias" aria-label="Titulares de medios externos">
        {tarjetas or '<div class="vacio">No hay titulares recientes disponibles.</div>'}
      </section>
    </main>"""
    extra_head = '<link rel="canonical" href="https://cevnoticias.com/actualidad.html"><meta property="og:type" content="website">'
    pagina = plantilla(
        "Más actualidad",
        contenido,
        "Titulares recientes de medios externos, identificados y enlazados a sus fuentes originales.",
        ruta_raiz="",
        extra_head=extra_head,
        seccion_actual=""
    )
    (SITE / "actualidad.html").write_text(pagina, encoding="utf-8")


def lista_vertical(noticias, titulares, categoria=None, excluir=None, ruta_raiz=""):
    excluir = excluir or set()
    elementos = []
    for noticia in noticias:
        if noticia.get("id") in excluir or (categoria and noticia.get("categoria") != categoria):
            continue
        elementos.append((fecha_ordenable(noticia), tarjeta(noticia, ruta_raiz=ruta_raiz)))
    for titular in titulares:
        if categoria and titular.get("categoria") != categoria:
            continue
        if titular.get("id") in excluir:
            continue
        elementos.append((fecha_ordenable(titular), tarjeta_rss(titular)))
    elementos.sort(key=lambda elemento: elemento[0], reverse=True)
    return "".join(html_card for _, html_card in elementos)


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS", ruta_raiz="", extra_head="", seccion_actual=""):
    enlaces = "".join(
        f'<a data-seccion="{slug(s)}" class="{"nav-activa" if slug(s) == slug(seccion_actual) else ""}" href="{ruta_raiz}secciones/{slug(s)}.html" {"aria-current=page" if slug(s) == slug(seccion_actual) else ""}>{escapar(s)}</a>'
        for s in SECCIONES
    )
    portada_activa = "nav-activa" if seccion_actual == "Portada" else ""
    portada_aria = 'aria-current="page"' if seccion_actual == "Portada" else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<!-- Google Analytics 4 solo se carga después de aceptar la analítica opcional. -->
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f7f6f2">
<meta name="description" content="{escapar(descripcion)}">
{extra_head}
<title>{escapar(titulo)} | CEV NOTICIAS</title>
<!-- Tipografías del sistema: no se contactan proveedores externos antes del consentimiento. -->
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
.nav-carrusel{{width:100%;max-width:980px;margin:0 auto;padding:0 18px;display:grid;grid-template-columns:34px minmax(0,1fr) 34px;gap:10px;align-items:center}}
.nav-interior{{width:100%;min-width:0;max-width:100%;margin:0;display:flex;flex-wrap:nowrap;align-items:center;justify-content:flex-start;gap:8px;padding:9px 2px;overflow-x:auto;overflow-y:hidden;white-space:nowrap;scrollbar-width:none;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scroll-behavior:smooth;scroll-snap-type:x proximity;}}
.nav-interior::-webkit-scrollbar{{display:none}}
.nav-interior a{{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;padding:10px 13px;border-bottom:3px solid transparent;border-radius:3px 3px 0 0;scroll-snap-align:start;transition:background .18s ease,color .18s ease,border-color .18s ease}}
.nav-interior a.nav-activa{{color:var(--rojo);background:#f5e7e7;border-bottom-color:var(--rojo);font-weight:800}}
.nav-flecha{{width:34px;height:34px;border:1px solid var(--linea);border-radius:50%;background:transparent;color:var(--tinta);font:700 21px/1 'DM Sans',sans-serif;cursor:pointer;transition:all .18s ease}}
.nav-flecha:hover:not(:disabled){{border-color:var(--rojo);background:#f5e7e7;color:var(--rojo)}}
.nav-flecha:disabled{{opacity:.28;cursor:default}}
nav a{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px}}
nav a:hover,nav a:focus{{color:var(--rojo)}}
body.noche .nav-interior a.nav-activa{{color:#ff858a;background:#3a2426;border-bottom-color:#ff858a}}
body.noche .nav-flecha{{border-color:#555;color:var(--tinta)}}
body.noche .nav-flecha:hover:not(:disabled){{background:#3a2426;border-color:#ff858a;color:#ff858a}}
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
.contador-noticias{{flex:none;color:var(--rojo);font:800 10px 'DM Sans',Arial,sans-serif;letter-spacing:1px;text-transform:uppercase;white-space:nowrap}}
.nota-rss-publica{{max-width:900px;margin:-8px 0 20px;color:var(--suave);font-size:12px;line-height:1.6}}
.tarjeta.titular-externo{{min-height:220px}}
.tarjeta.titular-externo .tarjeta-contenido{{display:flex;flex:1;flex-direction:column;align-items:flex-start;gap:12px}}
.tarjeta.titular-externo h3{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(18px,1.8vw,22px);line-height:1.2;margin:0}}
.tarjeta.titular-externo .rss-datos{{margin-top:auto}}
.tarjeta.titular-externo .rss-sello{{line-height:1.4}}
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
.nav-interior{{justify-content:flex-start;overflow-x:auto;scroll-behavior:smooth}}
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
.express-leer{{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo)}}.express-texto small{{font-size:9px;color:var(--suave)}}
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
.tarjeta-vertical.tarjeta-sin-imagen .tarjeta-enlace{{display:block}}
.tarjeta-vertical.tarjeta-sin-imagen .tarjeta-contenido{{padding:4px 0}}
.express-enlace.sin-imagen{{grid-template-columns:minmax(0,1fr)}}
.tarjeta-vertical .tarjeta-imagen img{{width:100%;height:100%;object-fit:cover}}
.tarjeta-vertical .tarjeta-contenido{{padding:0}}
.tarjeta-vertical h3{{font-size:clamp(22px,2.5vw,31px);line-height:1.14;margin:9px 0}}
.tarjeta-vertical p{{font-size:13px;line-height:1.7;max-width:760px;margin:8px 0 14px}}
.tarjeta-vertical .leer{{display:inline-block;margin-top:5px}}
.tarjeta-vertical.titular-externo{{display:block;min-height:0;background:transparent;border:0;border-bottom:1px solid var(--linea)}}
.tarjeta-vertical.titular-externo h3{{font-family:'Playfair Display',Georgia,serif}}
.tarjeta-vertical .titular-rss-enlace{{padding:0;gap:0}}
.portada-ficha{{max-width:740px;height:auto;margin:25px auto}}
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
.pie-enlaces{{display:flex;flex-wrap:wrap;justify-content:center;gap:10px 22px;margin:18px auto 0;max-width:760px}}
.pie-enlaces a{{color:#eee;font-size:11px;text-decoration:underline;text-decoration-color:#777;text-underline-offset:4px}}
.pie-enlaces a:hover{{color:#ff858a}}
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
 .nav-carrusel{{padding:0 9px;grid-template-columns:30px minmax(0,1fr) 30px;gap:6px}}
 .nav-flecha{{width:30px;height:30px;font-size:19px}}
 .nav-interior{{padding:9px 1px;gap:6px}}
 .nav-interior a{{padding:9px 11px;font-size:10px}}
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
.cev-cookie-banner{{position:fixed;z-index:10000;left:18px;bottom:18px;width:min(680px,calc(100vw - 36px));max-height:min(78vh,560px);overflow:auto;background:#fff;color:#171717;border:1px solid #cfc9bf;border-top:4px solid #b5282f;border-radius:10px;box-shadow:0 12px 38px rgba(0,0,0,.22);padding:20px;font:14px/1.55 'DM Sans',Arial,sans-serif}}
.cev-cookie-banner h2{{font:700 19px/1.2 'Playfair Display',Georgia,serif;margin:0 0 8px;color:#171717}}
.cev-cookie-banner p{{margin:7px 0;color:#444;font-size:13px}}
.cev-cookie-banner a{{text-decoration:underline;text-underline-offset:3px;color:#8e1e25}}
.cev-cookie-actions{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}}
.cev-cookie-actions button,.cev-cookie-options button{{border:1px solid #242424;border-radius:5px;padding:10px 13px;background:#fff;color:#171717;font:700 12px 'DM Sans',Arial,sans-serif;cursor:pointer}}
.cev-cookie-actions .principal{{background:#b5282f;border-color:#b5282f;color:#fff}}
.cev-cookie-actions button:hover,.cev-cookie-options button:hover{{filter:brightness(.95)}}
.cev-cookie-options{{margin-top:14px;padding-top:13px;border-top:1px solid #dedbd4}}
.cev-cookie-options label{{display:flex;align-items:flex-start;gap:9px;margin:10px 0;font-size:13px}}
.cev-cookie-options input{{margin-top:3px;accent-color:#b5282f}}
.cev-cookie-settings{{border:0;background:transparent;color:inherit;text-decoration:underline;text-underline-offset:3px;cursor:pointer;font:inherit;padding:5px 0}}
body.noche .cev-cookie-banner{{background:#202020;color:#f5f5f5;border-color:#555}}
body.noche .cev-cookie-banner h2,body.noche .cev-cookie-banner p{{color:#f1f1f1}}
body.noche .cev-cookie-actions button,body.noche .cev-cookie-options button{{background:#292929;color:#fff;border-color:#aaa}}
body.noche .cev-cookie-actions .principal{{background:#b5282f;border-color:#b5282f}}
@media(max-width:600px){{
 .cev-cookie-banner{{left:10px;bottom:10px;width:calc(100vw - 20px);padding:15px}}
 .cev-cookie-actions{{display:grid;grid-template-columns:1fr}}
 .cev-cookie-actions button{{width:100%}}
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
 <nav aria-label="Secciones">
  <div class="nav-carrusel">
   <button class="nav-flecha" id="nav-anterior" type="button" aria-label="Desplazar secciones hacia la izquierda">‹</button>
   <div class="nav-interior" id="nav-secciones" tabindex="0">
    <a data-seccion="portada" class="{portada_activa}" href="{ruta_raiz}" {portada_aria}>Portada</a>{enlaces}
   </div>
   <button class="nav-flecha" id="nav-siguiente" type="button" aria-label="Desplazar secciones hacia la derecha">›</button>
  </div>
 </nav>
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
 <nav class="pie-enlaces" aria-label="Información institucional">
  <a href="{ruta_raiz}quienes-somos.html">Quiénes somos</a>
  <a href="{ruta_raiz}redaccion.html">Redacción</a>
  <a href="{ruta_raiz}contacto.html">Contacto</a>
  <a href="{ruta_raiz}politica-editorial.html">Política editorial</a>
  <a href="{ruta_raiz}correcciones.html">Correcciones</a>
  <a href="{ruta_raiz}politica-de-privacidad.html">Privacidad y cookies</a>
 </nav>
 <button type="button" class="cev-cookie-settings" id="cev-cookie-settings">Configurar cookies</button>
</footer>

<section class="cev-cookie-banner" id="cev-cookie-banner" role="dialog" aria-modal="false" aria-labelledby="cev-cookie-title" aria-describedby="cev-cookie-description" hidden>
 <h2 id="cev-cookie-title">Privacidad y cookies</h2>
 <p id="cev-cookie-description">CEV NOTICIAS usa almacenamiento necesario para recordar tu elección. Google Analytics solo se activa si autorizas las cookies de analítica. Actualmente no mostramos publicidad ni activamos cookies publicitarias.</p>
 <p>Consulta nuestra <a href="{ruta_raiz}politica-de-privacidad.html">política de privacidad y cookies</a>.</p>
 <div class="cev-cookie-actions">
  <button class="principal" id="cev-cookie-accept" type="button">Aceptar analítica</button>
  <button id="cev-cookie-reject" type="button">Rechazar opcionales</button>
  <button id="cev-cookie-configure" type="button" aria-expanded="false" aria-controls="cev-cookie-options">Configurar</button>
 </div>
 <div class="cev-cookie-options" id="cev-cookie-options" hidden>
  <label><input type="checkbox" checked disabled> Almacenamiento necesario para recordar tu elección (siempre activo).</label>
  <label><input type="checkbox" id="cev-cookie-analytics"> Analítica opcional: permite que Google Analytics mida el uso del sitio.</label>
  <button id="cev-cookie-save" type="button">Guardar preferencias</button>
 </div>
</section>

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
 const nav=document.getElementById('nav-secciones');
 const navAnterior=document.getElementById('nav-anterior');
 const navSiguiente=document.getElementById('nav-siguiente');
 if(nav){{
  const maxScroll=()=>Math.max(0,nav.scrollWidth-nav.clientWidth);
  const actualizarNav=()=>{{
   const maximo=maxScroll();
   if(navAnterior)navAnterior.disabled=maximo<=4||nav.scrollLeft<=2;
   if(navSiguiente)navSiguiente.disabled=maximo<=4||nav.scrollLeft>=maximo-2;
  }};
  const moverNav=(direccion)=>{{
   const maximo=maxScroll();
   if(maximo<=4){{actualizarNav();return;}}
   const paso=Math.max(180,Math.round(nav.clientWidth*0.72));
   const inicio=nav.scrollLeft;
   const destino=Math.max(0,Math.min(maximo,inicio+(direccion*paso)));
   nav.scrollTo({{left:destino,behavior:'smooth'}});
   window.setTimeout(()=>{{
    if(Math.abs(nav.scrollLeft-inicio)<2)nav.scrollLeft=destino;
    actualizarNav();
   }},450);
  }};
  navAnterior?.addEventListener('click',()=>moverNav(-1));
  navSiguiente?.addEventListener('click',()=>moverNav(1));
  nav.addEventListener('scroll',actualizarNav,{{passive:true}});
  nav.addEventListener('scrollend',actualizarNav);
  nav.addEventListener('keydown',evento=>{{
   if(evento.key==='ArrowRight'){{evento.preventDefault();moverNav(1);}}
   if(evento.key==='ArrowLeft'){{evento.preventDefault();moverNav(-1);}}
  }});
  nav.querySelectorAll('a[data-seccion]').forEach(enlace=>{{
   enlace.addEventListener('click',()=>{{
    nav.querySelectorAll('a[data-seccion]').forEach(item=>{{
     item.classList.remove('nav-activa');
     item.removeAttribute('aria-current');
    }});
    enlace.classList.add('nav-activa');
    enlace.setAttribute('aria-current','page');
   }});
  }});
  const centrarActiva=()=>{{
   const activa=nav.querySelector('.nav-activa');
   if(!activa)return;
   const rectNav=nav.getBoundingClientRect();
   const rect=activa.getBoundingClientRect();
   const objetivo=nav.scrollLeft+(rect.left-rectNav.left)-(nav.clientWidth-rect.width)/2;
   nav.scrollTo({{left:Math.max(0,Math.min(maxScroll(),objetivo)),behavior:'auto'}});
  }};
  const recalcular=()=>{{centrarActiva();actualizarNav();}};
  window.addEventListener('resize',recalcular);
  window.addEventListener('load',recalcular,{{once:true}});
  if('ResizeObserver' in window){{new ResizeObserver(actualizarNav).observe(nav);}}
  requestAnimationFrame(recalcular);
  document.fonts?.ready?.then(recalcular);
 }}
 const barra=document.getElementById('progreso-lectura'),arriba=document.getElementById('volver-arriba');
 function actualizar(){{const max=document.documentElement.scrollHeight-window.innerHeight;if(barra)barra.style.width=(max>0?(window.scrollY/max)*100:0)+'%';if(arriba)arriba.hidden=window.scrollY<450;}}
 window.addEventListener('scroll',actualizar,{{passive:true}});actualizar();
 if(arriba)arriba.addEventListener('click',()=>window.scrollTo({{top:0,behavior:'smooth'}}));
}})();
</script>
<script src="{ruta_raiz}cookies.js" defer></script>
</body>
</html>"""


def crear_articulo(noticia, noticias=None):
    identificador = noticia["id"]
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    contenido = str(noticia.get("contenido") or "").strip()
    imagen = foto_local_noticia(noticia)
    foto = imagen_noticia(noticia, alt=titulo, clase="foto", loading="eager")
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
            f'<article class="tarjeta"><a class="tarjeta-enlace" href="/notas/{html.escape(otra.get("id", ""), quote=True)}.html"><span class="etiqueta">{escapar(otra.get("categoria"))}</span><h3>{escapar(otra.get("titulo"))}</h3><p>{escapar(otra.get("resumen"))}</p><span class="leer">Leer noticia ↗</span></a></article>'
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
       <a class="volver" href="/">← Volver a la portada</a>
       <p class="etiqueta">{categoria}</p>
       <h1>{titulo}</h1>
       <p class="bajada">{resumen}</p>
       <p class="fecha">Publicado: {escapar(noticia.get("fecha", fecha_actual()))} · Por <a href="../redaccion.html">CEV NOTICIAS</a></p>
       <p class="fecha">Fuentes consultadas: {len(noticia.get("fuentes", []))}</p>
      </div>
      {foto}
      {atribucion_imagen}
      <div class="cuerpo">{parrafos}</div>
      <div class="fuentes"><strong>Fuentes consultadas</strong><ul>{''.join(referencias)}</ul>
       <p>Contenido elaborado por CEV NOTICIAS a partir de las fuentes identificadas. Consulta las publicaciones originales para ampliar la información y contrastar los datos.</p>
      </div>
      {bloque_relacionadas}
    </main>"""
    url_articulo = f"https://cevnoticias.com/notas/{identificador}.html"
    datos_schema = {"@context":"https://schema.org","@type":"NewsArticle","headline":str(noticia.get("titulo","")),"description":str(noticia.get("resumen","")),"author":{"@type":"Organization","name":"CEV NOTICIAS"},"publisher":{"@type":"Organization","name":"CEV NOTICIAS"},"mainEntityOfPage":url_articulo}
    fecha_publicacion = fecha_schema(noticia)
    if fecha_publicacion:
        datos_schema["datePublished"] = fecha_publicacion
        datos_schema["dateModified"] = fecha_publicacion
    if imagen:
        datos_schema["image"] = imagen
    extra_head = f'<link rel="canonical" href="{url_articulo}"><meta property="og:type" content="article"><meta property="og:title" content="{titulo}"><meta property="og:description" content="{resumen}"><meta property="og:url" content="{url_articulo}">' + (f'<meta property="og:image" content="{imagen}">' if imagen else "") + '<script type="application/ld+json">' + json.dumps(datos_schema, ensure_ascii=False) + '</script>'
    pagina = plantilla(titulo, cuerpo, resumen, ruta_raiz="../", extra_head=extra_head, seccion_actual=noticia.get("categoria", ""))
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"{identificador}.html").write_text(pagina, encoding="utf-8")


def crear_pagina_titular_rss(titular):
    identificador = escapar(titular.get("id"))
    titulo = escapar(titular.get("titulo"))
    categoria = escapar(titular.get("categoria"))
    fuente = escapar(titular.get("fuente", "Medio de origen"))
    url_original = imagen_segura(titular.get("url"))
    imagen = imagen_segura(titular.get("imagen"))
    foto = f'<img class="foto" src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else ""
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p") if fecha else "Fecha no disponible"

    cuerpo = f"""
    <main class="articulo ficha-actualidad">
      <div class="articulo-cabecera">
        <a class="volver" href="/">← Volver a CEV NOTICIAS</a>
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
        <p class="nota-atribucion">CEV NOTICIAS identifica el medio de origen y enlaza a su cobertura. El contenido completo pertenece a la publicación citada.</p>      </section>
    </main>"""

    extra_head = '<meta name="robots" content="noindex,follow">'
    pagina = plantilla(
        titulo,
        cuerpo,
        "Titular de actualidad recopilado por CEV NOTICIAS con crédito al medio original.",
        ruta_raiz="../",
        extra_head=extra_head,
        seccion_actual=categoria
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
      <a class="volver" href="/">← Volver a la portada</a>
      <header class="cabecera-seccion">
        <p class="etiqueta">CEV NOTICIAS · SECCIÓN</p>
        <h1>{nombre}</h1>
        <p>Las noticias más recientes de {nombre}, organizadas en orden de publicación.</p>
      </header>
      <section class="lista-noticias" aria-label="Noticias de {nombre}">
        {listado}
      </section>
    </main>"""
    url_seccion = f"https://cevnoticias.com/secciones/{slug_seccion}.html"
    extra_head = f'<link rel="canonical" href="{url_seccion}"><meta property="og:type" content="website">'
    pagina = plantilla(
        seccion,
        cuerpo,
        f"Noticias de {seccion} en CEV NOTICIAS.",
        ruta_raiz="../",
        extra_head=extra_head,
        seccion_actual=seccion
    )
    carpeta = SITE / "secciones"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{slug_seccion}.html").write_text(pagina, encoding="utf-8")






def crear_paginas_institucionales():
    """Genera páginas públicas de identidad, contacto, privacidad y responsabilidad editorial."""
    paginas = {
        "redaccion.html": (
            "Redacción CEV NOTICIAS",
            "Conoce la autoría institucional y los criterios de preparación de los artículos de CEV NOTICIAS.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · AUTORÍA</p><h1>Redacción CEV NOTICIAS</h1>
              <div class="cuerpo">
                <p><strong>CEV NOTICIAS</strong> es un proyecto digital independiente de carácter personal. Actualmente no está constituido como empresa ni como sociedad.</p>
                <p>La firma institucional <strong>Redacción CEV NOTICIAS</strong> identifica la autoría editorial de las publicaciones que no llevan la firma de una persona. Su uso no significa que exista una plantilla o un equipo de periodistas: es la firma del medio.</p>
                <p>Los contenidos pueden apoyarse en herramientas automatizadas para localizar fuentes públicas, organizar información y preparar borradores. Antes de incorporarse a la edición pública, los nuevos artículos pasan por una revisión humana breve de titular, datos principales, fuentes y pertinencia de la imagen. Esta revisión no constituye una garantía absoluta de que no existan errores. Las fuentes consultadas se identifican en cada publicación.</p>
                <p>Para consultas editoriales, puedes escribir a <a href="mailto:cevnoticiascontacto@gmail.com">cevnoticiascontacto@gmail.com</a>.</p>
                <p>Cuando un artículo tenga un autor individual, su nombre y la información profesional correspondiente deberán aparecer en la propia publicación. Para conocer nuestros criterios, consulta la <a href="/politica-editorial.html">Política editorial</a>.</p>
              </div></main>"""
        ),
        "quienes-somos.html": (
            "Quiénes somos",
            "Conoce el propósito, el enfoque informativo y el alcance de CEV NOTICIAS.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · EL MEDIO</p><h1>Quiénes somos</h1>
              <div class="cuerpo">
                <p><strong>CEV NOTICIAS</strong> es un proyecto digital independiente de carácter personal, no constituido como empresa ni sociedad. Es un medio de actualidad con especial atención a Cali y el Valle del Cauca, Colombia y los acontecimientos internacionales de interés para el público hispanohablante.</p>
                <p>Nuestro propósito es facilitar el acceso a información reciente mediante noticias organizadas por temas, contexto y referencias a las fuentes consultadas.</p>
                <h2>Qué publicamos</h2><p>Cubrimos actualidad local, regional, nacional e internacional, además de deportes, tecnología, economía y tendencias. La selección de temas responde a su relevancia pública y a la disponibilidad de información verificable.</p>
                <h2>Cómo trabajamos</h2><p>Utilizamos fuentes identificables y herramientas digitales para apoyar el seguimiento de la actualidad y la preparación de contenidos. La automatización puede ayudar a recopilar y organizar información, pero no constituye por sí sola una verificación independiente. Los artículos nuevos pasan por una aprobación humana breve antes de publicarse. Identificamos las fuentes disponibles y ofrecemos un canal para reportar errores o solicitar aclaraciones.</p>
                <p>Cuando una publicación es un titular recopilado y no un artículo propio, se identifica como tal y se enlaza al medio de origen.</p>
              </div></main>"""
        ),
        "contacto.html": (
            "Contacto",
            "Canales para comunicarse con CEV NOTICIAS y enviar consultas editoriales.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · COMUNICACIÓN</p><h1>Contacto</h1>
              <div class="cuerpo">
                <p>CEV NOTICIAS es un proyecto digital independiente de carácter personal y actualmente no está constituido como empresa ni sociedad.</p>
                <p>Para noticias, consultas, propuestas de colaboración, solicitudes de prensa o asuntos relacionados con tus datos personales, escribe a nuestro correo oficial: <a href="mailto:cevnoticiascontacto@gmail.com"><strong>cevnoticiascontacto@gmail.com</strong></a>.</p>
                <p>También puedes comunicarte mediante Instagram: <a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">@cev.noticias</a>.</p>
                <p>Para reportar un posible error, incluye el enlace exacto de la publicación, una descripción clara del dato que debe revisarse y, si es posible, documentos o enlaces que respalden la solicitud.</p>
                <p>La recepción de un mensaje no implica que su contenido vaya a publicarse. La información enviada podrá ser revisada antes de utilizarse.</p>
              </div></main>"""
        ),
        "politica-de-privacidad.html": (
            "Política de privacidad y cookies",
            "Información sobre cookies, medición de audiencia, datos técnicos y privacidad en CEV NOTICIAS.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · TRANSPARENCIA</p><h1>Política de privacidad y cookies</h1>
              <div class="cuerpo">
                <p><strong>Última actualización:</strong> 3 de noviembre de 2026.</p>
                <h2>1. Responsable y alcance</h2><p><strong>Responsable del tratamiento:</strong> Johan Fabián Balluís, persona natural que administra CEV NOTICIAS como proyecto digital independiente. CEV NOTICIAS no está constituido actualmente como empresa ni como sociedad.</p><p><strong>Domicilio:</strong> Cali, Valle del Cauca, Colombia.</p><p><strong>Dirección de correspondencia:</strong> Calle 70B #43-70, Cali, Valle del Cauca, Colombia.</p><p><strong>Correo electrónico de contacto:</strong> <a href="mailto:htfg35129@gmail.com">htfg35129@gmail.com</a>.</p><p><strong>Teléfono de contacto:</strong> <a href="tel:+573019791129">301 979 1129</a>.</p><p><strong>Canal institucional alternativo:</strong> <a href="mailto:cevnoticiascontacto@gmail.com">cevnoticiascontacto@gmail.com</a>.</p><p>Estos canales están disponibles para consultas, peticiones y reclamos relacionados con el tratamiento de datos personales. Esta política explica qué información puede tratarse al visitar cevnoticias.com o al comunicarse voluntariamente con el medio. No se ofrece un formulario de registro ni se solicita crear una cuenta para leer las publicaciones.</p>
                <h2>2. Información y finalidades</h2><p>Si aceptas la analítica opcional, Google Analytics puede tratar datos técnicos y de uso, como páginas visitadas, duración aproximada de la visita, tipo de dispositivo y navegador, fuente de llegada y ubicación geográfica aproximada. Si escribes al correo o a Instagram, podremos tratar los datos que decidas incluir —por ejemplo, nombre de usuario, dirección de correo, contenido del mensaje y archivos adjuntos— para responder consultas, recibir información periodística, revisar reportes de errores y gestionar solicitudes.</p><p>Evita enviar datos sensibles o información de terceros que no sea necesaria. No utilizamos los mensajes recibidos para publicar datos personales sin una revisión de pertinencia y una base legítima para hacerlo.</p>
                <h2>3. Medición de audiencia</h2><p>Google Analytics 4 solo se carga después de que el visitante acepta expresamente la analítica opcional. Si la rechaza, la etiqueta de Google no se carga y no se envían datos de Analytics. Si posteriormente retira su elección desde «Configurar cookies», se actualiza el estado de consentimiento y el sitio intenta eliminar las cookies de Analytics que estén disponibles en el dominio.</p><p>Cuando se autoriza la medición, Google puede tratar identificadores en línea, datos de dispositivo, eventos de navegación y otros datos técnicos conforme a la configuración del servicio y sus propias políticas. Más información: <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Política de privacidad de Google</a> y <a href="https://support.google.com/analytics/answer/6004245" target="_blank" rel="noopener noreferrer">cómo protege Google Analytics los datos</a>.</p>
                <h2>4. Cookies y tecnologías similares</h2><p>El sitio utiliza almacenamiento local del navegador para recordar la preferencia de consentimiento. Este almacenamiento es necesario para respetar la elección del visitante en páginas posteriores. Las cookies de analítica de Google Analytics (por ejemplo, identificadores que comienzan por «_ga») solo se habilitan cuando el visitante acepta la opción de analítica. Puedes rechazarla o cambiar tu decisión desde el botón «Configurar cookies» del pie de página. También puedes borrar los datos guardados desde la configuración de tu navegador; al hacerlo, volverá a mostrarse el aviso de consentimiento.</p>
                <h2>5. Publicidad de terceros</h2><p>A la fecha de esta actualización, CEV NOTICIAS no tiene código de anuncios de Google AdSense implementado ni instala cookies publicitarias. Si en el futuro se incorporan anuncios u otros proveedores publicitarios, esta política se actualizará para identificar las tecnologías y finalidades pertinentes. Antes de activar publicidad se implementará una CMP certificada por Google e integrada con el TCF cuando resulte exigible para visitantes del Espacio Económico Europeo, Reino Unido y Suiza, además de los demás avisos y mecanismos de consentimiento aplicables.</p>
                <h2>6. Proveedores y enlaces externos</h2><p>Google presta el servicio de medición de audiencia bajo sus propias condiciones y políticas. Las noticias también pueden enlazar a sitios de terceros. CEV NOTICIAS no controla las políticas de privacidad, cookies ni prácticas de tratamiento de esos sitios; consulta sus avisos antes de compartir información.</p>
                <h2>7. Conservación y seguridad</h2><p>Los mensajes recibidos se conservarán durante el tiempo necesario para responder, tramitar la solicitud y mantener un registro razonable de la gestión, salvo que exista una obligación legal de conservación por más tiempo. Se procurará limitar el acceso a la información y evitar su divulgación no autorizada. Los periodos de conservación de datos gestionados por proveedores externos, como Google Analytics, se rigen también por la configuración disponible en esos servicios.</p>
                <h2>8. Derechos y solicitudes</h2><p>Cuando resulte aplicable la legislación colombiana de protección de datos personales, puedes solicitar conocer, actualizar y rectificar tus datos; pedir información sobre su uso; solicitar prueba de la autorización cuando corresponda; presentar consultas o reclamos; y solicitar la revocatoria de la autorización o la supresión del dato en los casos previstos por la ley.</p><p>Para presentar una consulta o reclamo, escribe a <a href="mailto:cevnoticiascontacto@gmail.com">cevnoticiascontacto@gmail.com</a>. Incluye el asunto «Protección de datos», describe claramente tu petición y aporta la información mínima necesaria para localizar los datos. También puedes utilizar Instagram <a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">@cev.noticias</a>. Las personas titulares pueden acudir a la Superintendencia de Industria y Comercio cuando proceda, después de agotar la consulta o reclamo ante el responsable.</p>
                <h2>9. Cambios</h2><p>Esta política puede modificarse para reflejar cambios técnicos, legales o de servicios. La fecha de actualización aparecerá al inicio de esta página. Para preguntas sobre privacidad, utiliza el correo oficial indicado en esta política.</p>
              </div></main>"""
        ),
        "politica-editorial.html": (
            "Política editorial",
            "Criterios de selección, fuentes, automatización, atribución y transparencia de CEV NOTICIAS.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · CRITERIOS</p><h1>Política editorial</h1>
              <div class="cuerpo">
                <h2>1. Principios</h2><p>CEV NOTICIAS busca ofrecer información clara, relevante y atribuida. Procuramos distinguir los hechos confirmados, los datos preliminares, las opiniones y la información que continúa en desarrollo.</p>
                <h2>2. Fuentes y atribución</h2><p>Priorizamos documentos, comunicados y datos de primera mano cuando están disponibles, junto con medios y organizaciones identificables. Los enlaces a las fuentes se incluyen para que los lectores puedan consultar el material original. La existencia de varias fuentes no garantiza por sí sola que sean independientes ni que todos los datos estén confirmados.</p>
                <h2>3. Herramientas automatizadas y controles de publicación</h2><p>El seguimiento de fuentes y la preparación de artículos originales pueden apoyarse en sistemas automatizados y herramientas de inteligencia artificial. Estas herramientas pueden cometer errores, omitir contexto o interpretar incorrectamente una fuente. Antes de publicar, cada artículo debe superar controles de extensión, categoría, enlaces HTTPS, detección de duplicados y atribución de las fuentes; los temas sensibles requieren corroboración de medios independientes. Las fotografías sin licencia y atribución completas se excluyen. Los titulares de otros medios se muestran por separado, identifican su fuente y enlazan al contenido original; no se presentan como artículos propios. Las altas, ediciones y retiros solicitados manualmente desde el panel sí pasan por revisión antes de publicarse. Estos controles reducen riesgos, pero no garantizan que nunca existan errores.</p>
                <h2>4. Titulares recopilados y contenido propio</h2><p>Un titular que remite a una publicación externa no se presenta como una investigación propia de CEV NOTICIAS. Cuando elaboramos un artículo a partir de fuentes consultadas, identificamos esas fuentes y enlazamos a sus publicaciones. Respetamos los derechos de autor y no pretendemos atribuirnos fotografías ni textos ajenos.</p>
                <h2>5. Imágenes</h2><p>Procuramos utilizar imágenes con permisos de reutilización adecuados y mostrar la atribución o licencia cuando corresponda. Una imagen ilustrativa no debe interpretarse como prueba visual del hecho si no corresponde al acontecimiento descrito.</p>
                <h2>6. Publicidad y contenido patrocinado</h2><p>Si se incorporan anuncios, patrocinios o enlaces de afiliados, deberán distinguirse visualmente del contenido periodístico. La publicidad no debe confundirse con una noticia ni condicionar la presentación de los hechos.</p>
                <h2>7. Correcciones</h2><p>Si detectas un error factual, una atribución incorrecta o información desactualizada, consulta nuestra <a href="/correcciones.html">Política de correcciones</a> y envíanos los datos necesarios para revisarlo.</p>
              </div></main>"""
        ),
        "correcciones.html": (
            "Política de correcciones",
            "Cómo reportar errores, solicitar aclaraciones y comunicar información relevante a CEV NOTICIAS.",
            """<main class="articulo pagina-institucional">
              <a class="volver" href="/">← Volver a la portada</a>
              <p class="etiqueta">CEV NOTICIAS · RESPONSABILIDAD</p><h1>Política de correcciones</h1>
              <div class="cuerpo">
                <p>CEV NOTICIAS procura corregir errores factuales y aclarar información cuando se identifica que una publicación contiene datos incorrectos, incompletos o desactualizados.</p>
                <h2>Cómo reportar un error</h2><ol><li>Envía el enlace exacto de la noticia.</li><li>Indica qué dato consideras incorrecto y por qué.</li><li>Adjunta, si es posible, una fuente primaria, documento o referencia que permita comprobar la observación.</li><li>Incluye un medio de contacto si deseas recibir respuesta.</li></ol>
                <p>Puedes enviar la solicitud a nuestro correo oficial <a href="mailto:cevnoticiascontacto@gmail.com">cevnoticiascontacto@gmail.com</a> o mediante <a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Instagram @cev.noticias</a>.</p>
                <h2>Qué hacemos con la solicitud</h2><p>Revisaremos la información aportada y, cuando corresponda, actualizaremos el contenido o añadiremos una aclaración. No todas las solicitudes implican una modificación: la decisión depende de la evidencia disponible. Si se realiza un cambio sustancial, procuraremos dejar constancia de la corrección en la publicación.</p>
              </div></main>"""
        )
    }
    for archivo, (titulo, descripcion, cuerpo) in paginas.items():
        url = f"https://cevnoticias.com/{archivo}"
        extra_head = f'<link rel="canonical" href="{url}"><meta property="og:type" content="website">'
        pagina = plantilla(titulo, cuerpo, descripcion, extra_head=extra_head)
        (SITE / archivo).write_text(pagina, encoding="utf-8")



def limpiar_archivos_publicos_obsoletos():
    """
    Limpia páginas, secciones e imágenes públicas de versiones anteriores.
    Conserva site/social porque contiene recursos aprobados para redes.
    """
    SITE.mkdir(parents=True, exist_ok=True)
    for nombre in ("notas", "secciones", "imagenes"):
        ruta = SITE / nombre
        if ruta.exists():
            shutil.rmtree(ruta)

    for nombre in ("index.html", "sitemap.xml", "robots.txt", "actualidad.html", "quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html"):
        ruta = SITE / nombre
        if ruta.exists():
            ruta.unlink()

    print("Archivos públicos antiguos eliminados; carpeta social conservada.")


def validar_archivos_publicados(noticias):
    """
    Comprueba que cada artículo, categoría e imagen apuntados exista
    físicamente dentro del artefacto que se va a desplegar.
    """
    faltantes = []
    esperados = [SITE / "index.html"]
    esperados.extend(SITE / nombre for nombre in ("actualidad.html", "quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html"))
    esperados.extend([SITE / "sitemap.xml", SITE / "robots.txt", SITE / "cookies.js"])
    esperados.extend(NOTAS / f"{noticia['id']}.html" for noticia in noticias)
    esperados.extend(SITE / "secciones" / f"{slug(seccion)}.html" for seccion in SECCIONES)
    esperados.extend(
        SITE / "imagenes" / f"{slug(noticia['id'])}{extension}"
        for noticia in noticias
        for extension in (".jpg", ".jpeg", ".png", ".webp", ".gif")
        if (SITE / "imagenes" / f"{slug(noticia['id'])}{extension}").exists()
    )

    for ruta in esperados:
        if not ruta.is_file() or ruta.stat().st_size == 0:
            faltantes.append(str(ruta.relative_to(SITE)))

    class RecolectorEnlaces(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, etiqueta, atributos):
            datos = dict(atributos)
            for campo in ("href", "src"):
                valor = datos.get(campo, "")
                if valor:
                    self.urls.append(valor)

    paginas = [SITE / "index.html"]
    paginas.extend(SITE / nombre for nombre in ("quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html"))
    paginas.extend(NOTAS / f"{noticia['id']}.html" for noticia in noticias)
    paginas.extend(SITE / "secciones" / f"{slug(seccion)}.html" for seccion in SECCIONES)

    for pagina in paginas:
        if not pagina.is_file():
            continue
        contenido_html = pagina.read_text(encoding="utf-8")
        if "portada-sin-foto" in contenido_html or "/social/" in contenido_html:
            faltantes.append(
                f"{pagina.relative_to(SITE)} contiene una portada de texto o un recurso social"
            )
        parser = RecolectorEnlaces()
        parser.feed(contenido_html)
        for url in parser.urls:
            if url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            partes = urlsplit(url)
            if partes.scheme in ("http", "https"):
                if (partes.hostname or "").lower() not in ("cevnoticias.com", "www.cevnoticias.com"):
                    continue
                destino_relativo = unquote(partes.path).lstrip("/")
                destino = (SITE / destino_relativo).resolve()
            elif partes.path.startswith("/"):
                destino = SITE / unquote(partes.path).lstrip("/")
            else:
                destino = (pagina.parent / unquote(partes.path)).resolve()

            destino = destino.resolve()
            if destino.is_dir():
                destino = destino / "index.html"
            try:
                destino.relative_to(SITE.resolve())
            except ValueError:
                continue
            if partes.path and not destino.is_file():
                faltantes.append(
                    f"{pagina.relative_to(SITE)} -> {url}"
                )

    for noticia in noticias:
        fuentes = noticia.get("fuentes", [])
        if not any(
            isinstance(fuente, dict)
            and urlsplit(str(fuente.get("url", ""))).scheme == "https"
            and urlsplit(str(fuente.get("url", ""))).hostname
            for fuente in fuentes
        ):
            faltantes.append(f"Artículo sin fuente HTTPS verificable: {noticia.get('id', 'sin-id')}")

    if faltantes:
        resumen = "\n".join(f" - {ruta}" for ruta in faltantes[:30])
        raise RuntimeError(
            "La validación detectó archivos o enlaces internos rotos:\n" + resumen
        )

    try:
        for archivo_contacto in ("contacto.html", "politica-de-privacidad.html", "correcciones.html", "redaccion.html"):
            contenido_contacto = (SITE / archivo_contacto).read_text(encoding="utf-8")
            if "cevnoticiascontacto@gmail.com" not in contenido_contacto:
                raise ValueError(f"{archivo_contacto} no incluye el correo oficial de contacto.")
        raiz_sitemap = ET.parse(SITE / "sitemap.xml").getroot()
        if raiz_sitemap.tag != "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset":
            raise ValueError("La raíz del sitemap no es urlset.")
        ns_sitemap = "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        if not any((elemento.text or "").strip() == "https://cevnoticias.com/" for elemento in raiz_sitemap.iter(ns_sitemap)):
            raise ValueError("El sitemap no incluye la portada.")
        robots = (SITE / "robots.txt").read_text(encoding="utf-8")
        if "Sitemap: https://cevnoticias.com/sitemap.xml" not in robots:
            raise ValueError("robots.txt no declara el sitemap.")
    except (ET.ParseError, OSError, ValueError) as error:
        raise RuntimeError(f"Validación SEO fallida: {error}") from error

    print(
        f"Validación completa: {len(noticias)} artículos, "
        f"{len(SECCIONES)} secciones, páginas institucionales, sitemap XML y rutas internas verificadas."
    )


def construir():
    limpiar_archivos_publicos_obsoletos()
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])
    radar = cargar_json(RADAR_RSS, {})
    titulares_rss = radar.get("titulares_rss", []) if isinstance(radar, dict) else []
    validas = []
    vistos = set()
    titulos_vistos = set()
    for noticia in noticias:
        titulo = str(noticia.get("titulo", "")).strip()
        contenido = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")
        if not titulo or len(contenido) < 250 or categoria not in SECCIONES:
            continue

        # No se publica un artículo sin al menos una fuente directa y enlazable.
        fuentes_validas = []
        for fuente in noticia.get("fuentes", []):
            if not isinstance(fuente, dict):
                continue
            url_fuente = str(fuente.get("url", "")).strip()
            partes_fuente = urlsplit(url_fuente)
            if (
                partes_fuente.scheme == "https"
                and partes_fuente.hostname
                and str(fuente.get("nombre", "")).strip()
                and str(fuente.get("titulo", "")).strip()
            ):
                fuentes_validas.append(fuente)
        if not fuentes_validas:
            print(f"Artículo omitido por falta de fuente HTTPS verificable: {titulo}")
            continue
        noticia["fuentes"] = fuentes_validas

        # Si los datos de licencia y atribución de la foto están incompletos,
        # se conserva el artículo, pero se publica sin fotografía.
        if noticia.get("imagen"):
            credito = noticia.get("imagen_credito") or {}
            campos_credito = ("autor", "fuente", "pagina", "licencia", "licencia_url")
            if not all(str(credito.get(campo, "")).strip() for campo in campos_credito):
                print(f"Fotografía omitida por falta de licencia o atribución completa: {titulo}")
                noticia["imagen"] = ""
                noticia["imagen_credito"] = {}

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
    titulares_publicos = seleccionar_titulares_publicos(titulares_rss, validas)
    print(
        f"Portada editorial: {len(validas)} artículos propios · "
        f"{len(titulares_publicos)} titulares atribuidos a medios externos."
    )

    for noticia in validas:
        crear_articulo(noticia, validas)

    SITE.mkdir(parents=True, exist_ok=True)
    # Los RSS se conservan solo como material de investigación interno; no se publican como noticias.
    principal = validas[0] if validas else None
    laterales = validas[1:4]
    if principal:
        visual = imagen_noticia(
            principal,
            alt=principal.get("titulo", ""),
            loading="eager",
            prioridad=True
        )
        bloque_imagen = f'<div class="destacada-visual">{visual}</div>' if visual else ""
        principal_html = f"""
        <article class="destacada">
         <a href="/notas/{escapar(principal['id'])}.html">
          {bloque_imagen}
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
             <a href="/notas/{escapar(noticia['id'])}.html">
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
    titulares_archivo = seleccionar_titulares_publicos(titulares_rss, validas, limite=None)
    for seccion in SECCIONES:
        crear_pagina_seccion(seccion, validas, titulares_archivo)
    crear_pagina_actualidad_externa(titulares_archivo)
    crear_paginas_institucionales()

    candidatos_express = []
    for noticia in validas:
        if principal and noticia["id"] == principal["id"]:
            continue
        item = dict(noticia)
        item["tipo"] = "propia"
        candidatos_express.append(item)
    candidatos_express.sort(key=fecha_ordenable, reverse=True)
    # Express recorre todas las noticias propias, no solo las primeras cinco.
    noticias_express = candidatos_express
    ids_express = {item["id"] for item in noticias_express}

    express_html = modulo_express(noticias_express)
    # La lista completa queda disponible bajo Express; las destacadas se repiten
    # allí para que ninguna noticia dependa exclusivamente del carrusel.
    lista_portada = lista_vertical(
        validas,
        [],
        excluir=({principal["id"]} if principal else set())
    )
    contenido = (
        f'{express_html}'
        '<main class="contenedor">'
        '<div class="cinta"><span>En desarrollo</span><span>Últimas noticias</span></div>'
        f'{portada}'
        '<section class="bloque-categoria" id="ultimas-noticias">'
        f'<h2 class="titulo-seccion">Noticias propias de CEV NOTICIAS <span class="contador-noticias">{len(validas)} artículos</span></h2>'
        f'<div class="lista-noticias">{lista_portada or "<div class=vacio>No hay noticias propias disponibles por ahora.</div>"}</div>'
        '</section>'
        '<section class="bloque-categoria" id="mas-actualidad">'
        f'<h2 class="titulo-seccion">Más actualidad en otros medios <span class="contador-noticias">{len(titulares_publicos)} titulares</span></h2>'
        '<p class="nota-rss-publica">Seguimiento de publicaciones recientes de medios externos. Cada titular conserva el crédito y dirige al artículo original; no representa una publicación de autoría propia de CEV NOTICIAS.</p>'
        f'<div class="rejilla rejilla-categorias">{lista_vertical([], titulares_publicos) or "<div class=vacio>No hay titulares externos recientes.</div>"}</div>'
        '<a class="boton" href="/actualidad.html">Ver todos los titulares de otros medios ↗</a>'
        '</section></main>'
    )
    portada_head = '<link rel="canonical" href="https://cevnoticias.com/"><meta property="og:type" content="website"><meta property="og:title" content="CEV NOTICIAS | Actualidad y periodismo">'
    (SITE / "index.html").write_text(plantilla("Portada", contenido, "Noticias de Cali, Valle del Cauca, Colombia y el mundo.", extra_head=portada_head, seccion_actual="Portada"), encoding="utf-8")
    recurso_cookies = BASE / "cookies.js"
    if not recurso_cookies.is_file():
        raise RuntimeError("No se encontró cookies.js; no se puede publicar el gestor de consentimiento.")
    shutil.copy2(recurso_cookies, SITE / "cookies.js")
    paginas_institucionales = ["quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html", "actualidad.html"]
    urls = (["https://cevnoticias.com/"]
            + [f"https://cevnoticias.com/notas/{n['id']}.html" for n in validas]
            + [f"https://cevnoticias.com/secciones/{slug(s)}.html" for s in SECCIONES]
            + [f"https://cevnoticias.com/{nombre}" for nombre in paginas_institucionales])
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + ''.join(f"  <url><loc>{html.escape(url)}</loc></url>\n" for url in urls)
               + '</urlset>\n')
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://cevnoticias.com/sitemap.xml\n", encoding="utf-8")
    validar_archivos_publicados(validas)
    print(f"Portada creada. Artículos propios: {len(validas)} · Titulares externos publicados: {len(titulares_publicos)} · Titulares RSS disponibles: {len(titulares_rss)}")


if __name__ == "__main__":
    construir()