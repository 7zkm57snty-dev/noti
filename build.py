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


def imagen_segura(url):
    url = str(url or "").strip()
    return escapar(url) if url.startswith(("https://", "http://")) else ""


def etiqueta_estado(noticia):
    estado = str(noticia.get("estado_informacion", "")).strip().lower()
    # El archivo histórico puede mostrar Confirmada si registra contraste
    # de varias fuentes independientes y no tiene un estado más específico.
    if not estado and "varias fuentes independientes" in str(noticia.get("verificacion", "")).lower():
        estado = "confirmada"
    etiquetas = {
        "confirmada": ("Confirmada", "confirmada"),
        "en_desarrollo": ("En desarrollo", "desarrollo"),
        "informacion_preliminar": ("Información preliminar", "preliminar")
    }
    # El resto del archivo histórico conserva el rótulo neutral Actualidad.
    texto, clase = etiquetas.get(estado, ("Actualidad", "actualidad"))
    return f'<span class="estado-noticia estado-{clase}" aria-label="Estado de la información: {texto}">{texto}</span>'


def tarjeta(noticia, posicion=0):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    imagen = imagen_segura(noticia.get("imagen"))
    identificador = escapar(noticia.get("id"))
    visual = f'<img src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else '<div class="imagen-vacia">CEV</div>'
    clase = " tarjeta-principal" if posicion == 0 else ""
    return f"""
    <article class="tarjeta{clase}">
      <a class="tarjeta-enlace" href="notas/{identificador}.html">
        <div class="tarjeta-imagen">{visual}</div>
        <div class="tarjeta-contenido">
          <span class="etiqueta">{categoria}</span>
          {etiqueta_estado(noticia)}
          <h3>{titulo}</h3>
          <p>{resumen}</p>
          <span class="leer">Leer noticia <span aria-hidden="true">↗</span></span>
        </div>
      </a>
    </article>"""


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS", ruta_raiz="", extra_head=""):
    datos_navegacion = cargar_json(CACHE, {})
    noticias_navegacion = datos_navegacion.get("noticias", []) if isinstance(datos_navegacion, dict) else []
    secciones_disponibles = {n.get("categoria") for n in noticias_navegacion if isinstance(n, dict)}
    enlaces = "".join(
        f'<a href="https://cevnoticias.com/#categoria-{slug(s)}">{escapar(s)}</a>'
        for s in SECCIONES if s in secciones_disponibles
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
.portada-grid{{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:30px;align-items:stretch;padding-bottom:27px;border-bottom:1px solid var(--tinta)}}
.destacada{{min-width:0}}
.destacada-visual{{height:340px;overflow:hidden;background:#e7e3dc}}
.destacada-visual img{{width:100%;height:100%;object-fit:cover;display:block}}
.destacada-visual .imagen-vacia{{height:100%}}
.destacada-texto{{padding:18px 4px 0 0}}
.etiqueta{{display:inline-block;color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase}}
.estado-informacion{{display:inline-block;margin:8px 0 2px;padding:5px 8px;border-left:2px solid #b88732;background:#f2eadb;color:#654b20;font-size:10px;font-weight:700;letter-spacing:.35px}}
.aviso-desarrollo{{max-width:var(--ancho);margin:0 auto 18px;padding:13px 16px;border:1px solid #d8c69f;border-left:4px solid #b88732;background:#f2eadb;color:#55472f;font-size:13px;line-height:1.65;font-weight:600}}
body.noche .aviso-desarrollo{{background:#302a20;border-color:#665333;border-left-color:#d0a65d;color:#f0e2c5}}
body.noche .estado-informacion{{background:#393124;color:#f0d49c;border-color:#d0a65d}}
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
 .rejilla{{display:flex;overflow-x:auto;scroll-snap-type:none;gap:14px;padding-bottom:12px;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}}
 .rejilla .tarjeta{{flex:0 0 84%;scroll-snap-align:none}}
 .rejilla .tarjeta-imagen{{height:190px}}
}}


/* Carruseles continuos por sección */
.bloque-categoria{{overflow:hidden}}
.rejilla.carrusel-infinito{{display:flex;gap:22px;overflow-x:auto;overflow-y:hidden;width:100%;max-width:100%;animation:none;scrollbar-width:none;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scroll-behavior:auto;scroll-snap-type:none;touch-action:pan-x;padding-bottom:12px}} .rejilla.carrusel-infinito::-webkit-scrollbar{{display:none}}

.rejilla.carrusel-infinito .tarjeta{{flex:0 0 clamp(245px,27vw,330px);width:clamp(245px,27vw,330px);min-width:0}}
.rejilla.carrusel-infinito .tarjeta-imagen{{height:185px}}


@media(max-width:650px){{
 .rejilla.carrusel-infinito{{gap:14px}}
 .rejilla.carrusel-infinito .tarjeta{{flex-basis:82vw;width:82vw}}
 .rejilla.carrusel-infinito .tarjeta-imagen{{height:190px}}
}}
@media(prefers-reduced-motion:reduce){{.rejilla.carrusel-infinito{{scroll-snap-type:x mandatory}}.rejilla.carrusel-infinito .tarjeta{{scroll-snap-align:start}}}}


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
/* Rediseño editorial CEV NOTICIAS */
.franja-editorial{{background:#17191d;color:#f8f7f3}}
.franja-editorial>div{{max-width:var(--ancho);margin:auto;padding:8px 28px;display:flex;justify-content:space-between;gap:16px;align-items:center;font-size:10px;letter-spacing:.7px;text-transform:uppercase}}
.franja-editorial strong{{color:#ef5960;letter-spacing:1.5px}}
.cabecera{{padding:22px 28px 16px;text-align:left}}
.brand-row{{display:flex;align-items:center;justify-content:space-between;gap:20px}}
.marca{{font-size:clamp(42px,5.8vw,66px);letter-spacing:-3px;line-height:.92}}
.eslogan{{margin-top:7px;letter-spacing:1.6px;text-align:left;font-size:10px}}
.instagram-marca{{margin:0 0 0 auto;padding:10px 13px;border:1px solid var(--linea);border-radius:3px}}
.cabecera-meta{{margin-top:17px;padding-top:10px}}
.nav-interior{{max-width:var(--ancho);padding:13px 28px;gap:clamp(14px,2vw,27px)}}
nav a{{font-size:10px;letter-spacing:1px}}
nav a[href$="institucional.html"],nav a[href$="boletin.html"]{{color:var(--rojo)}}
.barra-herramientas{{max-width:var(--ancho);padding:10px 28px;background:#eeece6}}
.buscador{{max-width:420px;border-radius:3px}}
.accion-ui{{border-radius:3px}}
.contenedor{{padding-bottom:30px}}
.cinta{{margin:22px 0 16px}}
.cinta>span{{font-size:11px}}
.portada-grid{{grid-template-columns:minmax(0,1.65fr) minmax(240px,.7fr);gap:28px;align-items:stretch;padding:0 0 30px;border-bottom:1px solid var(--tinta)}}
.destacada{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(260px,.9fr);background:#fff;border:1px solid #e1ded7;min-height:380px}}
.destacada-visual{{height:100%;min-height:380px;background:#dedbd4}}
.destacada-texto{{padding:28px 26px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}}
.destacada h1{{font-size:clamp(29px,3.1vw,43px);line-height:1.06;margin:12px 0}}
.destacada p{{font-size:13px;line-height:1.7}}
.destacada .boton{{margin-top:18px}}
.estado-noticia{{display:inline-flex;align-items:center;gap:6px;margin:8px 0 2px;padding:5px 9px;border-radius:2px;font-size:9px;font-weight:800;letter-spacing:.75px;text-transform:uppercase}}
.estado-noticia:before{{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}}
.estado-actualidad{{background:#edf0f2;color:#40515e}}
.estado-confirmada{{background:#e5f2e9;color:#23613b}}
.estado-desarrollo{{background:#f7eedb;color:#805d1d}}
.estado-preliminar{{background:#f6e4e3;color:#9b3438}}
.lateral{{padding:24px 21px;border:1px solid #e1ded7;border-left:3px solid var(--rojo);background:#fff}}
.lateral-titulo{{font-family:'Playfair Display',Georgia,serif;font-size:23px;letter-spacing:-.4px;text-transform:none;margin-bottom:14px}}
.lateral-titulo:before{{display:none}}
.lateral-intro{{font-size:12px;line-height:1.7;color:#676767;margin:0 0 18px}}
.lateral-enlace{{display:flex;justify-content:space-between;gap:10px;padding:14px 0;border-top:1px solid #e6e3dc;font-size:12px;font-weight:700}}
.lateral-enlace span{{color:var(--rojo)}}
.lateral-social{{display:block;margin-top:12px;padding:12px;background:#f5f2ec;color:#252525;font-size:11px;line-height:1.5}}
.bloque-categoria{{padding:29px 0 32px;border-bottom:1px solid var(--linea)}}
.titulo-seccion{{font-size:clamp(27px,3vw,36px);margin-bottom:17px}}
.titulo-seccion:before{{content:"";width:4px;height:25px;background:var(--rojo);display:inline-block;margin-right:1px;align-self:center}}
.rejilla{{grid-template-columns:repeat(3,minmax(0,1fr));gap:23px}}
.tarjeta{{background:#fff;border:1px solid #e4e1da;transition:transform .2s ease,box-shadow .2s ease}}
.tarjeta:hover{{transform:translateY(-3px);box-shadow:0 10px 25px rgba(30,30,30,.08)}}
.tarjeta-imagen{{height:175px}}
.tarjeta-contenido{{padding:14px 15px 17px}}
.tarjeta h3{{font-size:21px}}
.tarjeta p{{font-size:12px}}
.tarjeta .estado-noticia{{margin-top:9px}}
.pie{{margin-top:0;background:#17191d;padding:35px 24px}}
.pie-interior{{max-width:var(--ancho);margin:auto;display:grid;grid-template-columns:1.1fr 1fr;gap:24px;text-align:left}}
.pie-marca{{font-family:'Playfair Display',Georgia,serif;font-size:31px;font-weight:800}}
.pie-links{{display:flex;flex-wrap:wrap;justify-content:flex-end;align-content:start;gap:12px 20px;font-size:11px}}
.pie-links a{{color:#f3eee8}}
.pie-links a:hover{{color:#ff777d}}
.pie-legal{{grid-column:1/-1;border-top:1px solid #3a3d42;padding-top:15px;color:#b8b8b8!important}}
.pagina-editorial{{max-width:1000px;margin:0 auto;padding:48px 28px 70px}}
.pagina-editorial .sobrelinea{{color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase}}
.pagina-editorial h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(40px,6vw,65px);letter-spacing:-1.7px;line-height:1.02;margin:12px 0 17px}}
.pagina-editorial .entradilla{{max-width:760px;color:#5e5e5e;font-size:18px;line-height:1.7;margin-bottom:32px}}
.editorial-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
.editorial-card{{padding:23px;background:#fff;border:1px solid var(--linea)}}
.editorial-card h2{{font-family:'Playfair Display',Georgia,serif;font-size:23px;margin:0 0 10px}}
.editorial-card p,.editorial-card li{{font-size:13px;line-height:1.75;color:#5c5c5c}}
.editorial-card ul{{padding-left:18px}}
.boletin-fecha{{display:inline-block;margin:7px 0 25px;padding:7px 10px;background:#f0ede6;color:#555;font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase}}
.boletin-lista{{max-width:850px;display:grid;gap:0;border-top:1px solid var(--linea)}}
.boletin-item{{display:grid;grid-template-columns:115px 1fr;gap:18px;padding:19px 0;border-bottom:1px solid var(--linea)}}
.boletin-item .fecha{{font-size:10px;color:#858585}}
.boletin-item h2{{font-family:'Playfair Display',Georgia,serif;font-size:22px;line-height:1.2;margin:5px 0 7px}}
.boletin-item p{{font-size:12px;line-height:1.65;color:#666;margin:0}}
.boletin-cta{{margin-top:30px;padding:22px 24px;background:#202329;color:white;display:flex;align-items:center;justify-content:space-between;gap:18px}}
.boletin-cta p{{font-size:12px;line-height:1.6;color:#d1d1d1;margin:4px 0}}
.boletin-cta a{{white-space:nowrap;background:var(--rojo);padding:11px 15px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.7px}}
body.noche .franja-editorial,body.noche .pie{{background:#090a0c}}
body.noche .barra-herramientas{{background:#191a1c}}
body.noche .destacada,body.noche .lateral,body.noche .tarjeta,body.noche .editorial-card{{background:#222;border-color:#444}}
body.noche .lateral-intro,body.noche .editorial-card p,body.noche .editorial-card li,body.noche .boletin-item p,body.noche .pagina-editorial .entradilla{{color:#d0ccc4}}
body.noche .lateral-enlace{{border-color:#484848}}
body.noche .lateral-social,body.noche .boletin-fecha{{background:#303030;color:#eee}}
body.noche .boletin-cta{{background:#101114}}
body.noche .boletin-item{{border-color:#484848}}
body.noche .estado-actualidad{{background:#303b44;color:#d5e0e7}}
body.noche .estado-confirmada{{background:#233d2d;color:#a7e2b8}}
body.noche .estado-desarrollo{{background:#453923;color:#f0d49c}}
body.noche .estado-preliminar{{background:#482829;color:#f1b5b3}}
@media(max-width:900px){{
 .destacada{{grid-template-columns:1fr}}
 .destacada-visual{{height:300px;min-height:300px}}
 .destacada-texto{{padding:22px}}
 .rejilla{{grid-template-columns:repeat(2,minmax(0,1fr))}}
}}
@media(max-width:650px){{
 .franja-editorial>div{{padding:8px 15px;font-size:8px}}
 .franja-editorial>div span:nth-child(2){{display:none}}
 .cabecera{{padding:18px 15px 13px}}
 .brand-row{{align-items:flex-start;flex-wrap:wrap}}
 .marca{{font-size:47px;letter-spacing:-2.3px}}
 .eslogan{{font-size:9px}}
 .instagram-marca{{margin:4px 0 0 auto;padding:7px 9px}}
 .cabecera-meta{{font-size:9px}}
 .nav-interior{{padding:12px 15px}}
 .barra-herramientas{{padding:9px 15px}}
 .contenedor{{padding:0 15px 25px}}
 .portada-grid{{grid-template-columns:1fr;gap:14px}}
 .destacada{{grid-template-columns:1fr}}
 .destacada-visual{{height:225px;min-height:225px}}
 .destacada-texto{{padding:18px}}
 .destacada h1{{font-size:34px}}
 .lateral{{padding:19px}}
 .rejilla{{display:grid;grid-template-columns:1fr;gap:15px;overflow:visible}}
 .rejilla .tarjeta{{width:auto;flex:none}}
 .tarjeta{{display:grid;grid-template-columns:112px minmax(0,1fr);align-items:stretch}}
 .tarjeta-imagen{{height:100%;min-height:136px}}
 .tarjeta-contenido{{padding:10px 12px}}
 .tarjeta h3{{font-size:17px;margin:6px 0}}
 .tarjeta p{{font-size:11px;line-height:1.5;margin:6px 0}}
 .tarjeta .etiqueta{{font-size:8px}}
 .tarjeta .estado-noticia{{font-size:8px;padding:4px 6px;margin:5px 0}}
 .pie-interior{{grid-template-columns:1fr}}
 .pie-links{{justify-content:flex-start}}
 .pie-legal{{grid-column:auto}}
 .pagina-editorial{{padding:34px 17px 50px}}
 .editorial-grid{{grid-template-columns:1fr}}
 .boletin-item{{grid-template-columns:1fr;gap:5px}}
 .boletin-cta{{align-items:flex-start;flex-direction:column}}
 .boletin-cta a{{white-space:normal}}
}}

.destacada>a{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(260px,.9fr);height:100%}}
@media(max-width:900px){{.destacada>a{{grid-template-columns:1fr}}}}

/* Sistema editorial responsive: fotografías completas y jerarquía consistente */
.destacada>a{{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(270px,.92fr);height:100%;align-items:stretch}}
.destacada-visual{{height:auto;min-height:360px;aspect-ratio:4/3;background:#e9e6df;display:flex;align-items:center;justify-content:center}}
.destacada-visual img{{width:100%;height:100%;object-fit:contain;object-position:center;background:#e9e6df}}
.destacada-texto{{min-width:0}}
.portada-grid{{grid-template-columns:minmax(0,1.7fr) minmax(280px,.8fr);align-items:stretch;gap:24px}}
.lateral{{border:1px solid var(--linea);border-top:3px solid var(--rojo);border-left:1px solid var(--linea);padding:22px;background:#fff;display:flex;flex-direction:column;gap:10px}}
.lateral-kicker{{font-size:9px;font-weight:800;letter-spacing:1.5px;color:var(--rojo)}}
.lateral-titulo{{display:block;font-family:'Playfair Display',Georgia,serif;font-size:27px;line-height:1.1;text-transform:none;margin:0}}
.lateral-intro{{font-size:12px;line-height:1.65;color:#666;margin:0 0 4px}}
.explorar-secciones{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}
.explorar-chip{{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;background:#f4f2ed;border:1px solid #e8e4dc;font-size:11px;font-weight:700;min-width:0}}
.explorar-chip:hover{{border-color:var(--rojo);color:var(--rojo)}}
.explorar-chip small{{color:#777;font-size:10px}}
.lateral-destino{{padding:13px 0 0;border-top:1px solid var(--linea)}}
.lateral-destino strong{{font-family:'Playfair Display',Georgia,serif;font-size:18px}}
.lateral-destino p{{font-size:11px;color:#666;line-height:1.5;margin:5px 0}}
.lateral-destino a{{font-size:10px;font-weight:800;color:var(--rojo);text-transform:uppercase;letter-spacing:.6px}}
.feed-noticias{{margin-top:30px}}
.feed-noticias .titulo-seccion{{margin-bottom:18px}}
.ancla-seccion{{display:block;position:relative;top:-18px;scroll-margin-top:18px}}
.destacada-visual img,.tarjeta-imagen img,.articulo .foto{{object-fit:contain!important;object-position:center;background:#e9e6df}}
.tarjeta-imagen{{height:auto;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;background:#e9e6df}}
.tarjeta-imagen img{{width:100%;height:100%;object-fit:contain;display:block}}
.tarjeta{{display:flex;flex-direction:column;min-width:0;overflow:hidden}}
.tarjeta-enlace{{display:flex;flex-direction:column;height:100%}}
.tarjeta-contenido{{padding:14px 16px 17px}}
.tarjeta h3{{font-size:clamp(18px,1.55vw,22px);line-height:1.18}}
.tarjeta p{{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.rejilla.carrusel-infinito{{display:flex;align-items:stretch;gap:20px;overflow-x:auto;overflow-y:hidden;width:100%;max-width:100%;padding:0 0 14px;scrollbar-width:none;scroll-behavior:auto;scroll-snap-type:x proximity;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}}
.rejilla.carrusel-infinito::-webkit-scrollbar{{display:none}}
.rejilla.carrusel-infinito .tarjeta{{flex:0 0 clamp(270px,29vw,350px);width:clamp(270px,29vw,350px);min-width:0;scroll-snap-align:start}}
.rejilla.carrusel-infinito .tarjeta-imagen{{height:auto;aspect-ratio:16/9}}
.articulo .foto-marco{{margin:26px auto 8px;max-width:900px;max-height:72vh;background:#e9e6df;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.articulo .foto{{width:100%;height:auto;max-height:72vh;display:block;margin:0;object-fit:contain;object-position:center}}
.mapa-articulos{{grid-column:1/-1}}
.mapa-articulos ul{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px 28px;list-style:none;padding:0}}
.mapa-articulos li{{padding:10px 0;border-bottom:1px solid var(--linea)}}
.mapa-articulos small{{display:block;font-size:10px;color:#888;margin-top:4px}}
body.noche .lateral{{background:#222;border-color:#484848}}
body.noche .lateral-intro,body.noche .lateral-destino p{{color:#d0ccc4}}
body.noche .explorar-chip{{background:#303030;border-color:#484848;color:#eee}}
body.noche .destacada-visual img,body.noche .tarjeta-imagen img,body.noche .articulo .foto,body.noche .destacada-visual,body.noche .tarjeta-imagen{{background:#252525}}
@media(max-width:980px){{
 .portada-grid{{grid-template-columns:1fr}}
 .destacada>a{{grid-template-columns:minmax(0,1fr) minmax(260px,.9fr)}}
 .destacada-visual{{min-height:300px}}
 .lateral{{display:grid;grid-template-columns:1fr 1fr;gap:12px 18px}}
 .lateral-kicker,.lateral-titulo,.lateral-intro,.explorar-secciones{{grid-column:1/-1}}
 .lateral-destino{{margin-top:0}}
}}
@media(max-width:700px){{
 .franja-editorial>div{{padding:8px 14px;font-size:8px}}
 .cabecera{{padding:18px 15px 13px}}
 .brand-row{{align-items:center;gap:10px}}
 .marca{{font-size:clamp(39px,10vw,48px);letter-spacing:-2.2px}}
 .instagram-marca{{margin:0;padding:7px 9px}}
 .instagram-marca strong{{font-size:10px}}
 .instagram-marca small{{font-size:9px}}
 .cabecera-meta{{font-size:9px;gap:10px}}
 .nav-interior{{padding:12px 15px;gap:18px;overflow-x:auto}}
 .barra-herramientas{{padding:9px 15px;flex-wrap:nowrap}}
 .buscador{{max-width:none;flex:1;min-width:0}}
 .accion-ui{{white-space:nowrap;padding:9px 10px}}
 .contenedor{{padding:0 15px 24px}}
 .cinta{{margin:18px 0 13px}}
 .destacada>a{{grid-template-columns:1fr}}
 .destacada-visual{{height:auto;min-height:0;aspect-ratio:16/9}}
 .destacada-texto{{padding:18px 17px 20px}}
 .destacada h1{{font-size:clamp(27px,8vw,35px)}}
 .destacada p{{font-size:12px}}
 .lateral{{display:flex;padding:18px}}
 .lateral-titulo{{font-size:24px}}
 .explorar-secciones{{grid-template-columns:repeat(2,minmax(0,1fr))}}
 .feed-noticias{{margin-top:24px}}
 .rejilla.carrusel-infinito{{gap:13px;margin-right:-15px;padding-right:15px}}
 .rejilla.carrusel-infinito .tarjeta{{flex:0 0 min(82vw,350px);width:min(82vw,350px)}}
 .tarjeta-imagen{{aspect-ratio:16/9;height:auto}}
 .tarjeta-contenido{{padding:12px 13px 15px}}
 .tarjeta h3{{font-size:18px}}
 .tarjeta p{{font-size:11px;-webkit-line-clamp:3}}
 .pagina-editorial{{padding:32px 17px 48px}}
 .pagina-editorial h1{{font-size:clamp(36px,10vw,48px)}}
 .editorial-grid{{grid-template-columns:1fr}}
 .mapa-articulos ul{{grid-template-columns:1fr}}
 .pie-interior{{grid-template-columns:1fr}}
 .pie-links{{justify-content:flex-start}}
 .pie-legal{{grid-column:auto}}
 .articulo{{padding:0 17px;margin-top:22px}}
 .articulo h1{{font-size:clamp(34px,10vw,43px)}}
 .articulo .foto-marco{{margin:20px -2px 8px;max-height:60vh}}
 .articulo .foto{{max-height:60vh;width:100%}}
}}
@media(prefers-reduced-motion:reduce){{
 .rejilla.carrusel-infinito{{scroll-behavior:auto}}
 .tarjeta,.tarjeta-imagen img{{transition:none}}
}}

</style>
</head>
<body>
<div class="franja-editorial"><div><strong>CEV NOTICIAS</strong><span>Periodismo · Contexto · Actualidad</span><span>{fecha_actual()} · Cali, Colombia</span></div></div>
<header class="masthead">
 <div class="cabecera">
  <div class="brand-row">
   <div><div class="marca"><a href="{ruta_raiz}" aria-label="CEV NOTICIAS, ir al inicio">CEV <span>NOTICIAS</span></a></div><div class="eslogan">La actualidad, con contexto.</div></div>
   <a class="instagram-marca" href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer" aria-label="Instagram de Cali en Vivo Noticias: @cev.noticias"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.5" cy="6.8" r="1.1" fill="currentColor"/></svg><span><strong>Cali en Vivo Noticias</strong><small>@cev.noticias</small></span></a>
  </div>
  <div class="cabecera-meta"><span>Edición digital · Actualización permanente</span><span class="estado">Cali · Colombia</span></div>
 </div>
 <nav aria-label="Navegación principal"><div class="nav-interior">
  <a href="{ruta_raiz}">Portada</a>{enlaces}
  <a href="institucional.html">Quiénes somos</a><a href="boletin.html">Boletín</a>
 </div></nav>
 <div class="barra-herramientas">
  <input id="buscar-noticias" class="buscador" type="search" placeholder="Buscar noticias, temas o palabras..." aria-label="Buscar noticias">
  <button id="modo-noche" class="accion-ui" type="button" aria-pressed="false">◐ Modo oscuro</button>
 </div>
</header>
{contenido}
<footer class="pie">
 <div class="pie-interior">
  <div><div class="pie-marca">CEV <span>NOTICIAS</span></div><p>Actualidad de Cali, el Valle del Cauca, Colombia y el mundo.</p></div>
  <div class="pie-links"><a href="{ruta_raiz}">Portada</a><a href="institucional.html">Quiénes somos</a><a href="boletin.html">Boletín de noticias</a><a href="{ruta_raiz}mapa-del-sitio.html">Mapa del sitio</a><a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Instagram · @cev.noticias</a></div>
  <p class="pie-legal">CEV NOTICIAS · Las fuentes consultadas se identifican al final de cada artículo. Las noticias en desarrollo se actualizan cuando existen nuevos datos respaldados.</p>
 </div>
</footer>
<script>
(function(){{
 // Carruseles automáticos para navegación y noticias, sin clonar contenido.
 const selectores=['.rejilla.carrusel-infinito'];
 const carruseles=selectores.flatMap(selector=>[...document.querySelectorAll(selector)]);
 carruseles.forEach(track=>{{
  let pausado=false,anterior=0,direccion=1,reactivar=null,ultimoScroll=track.scrollLeft;
  const velocidad=64;
  const maximo=()=>Math.max(0,track.scrollWidth-track.clientWidth);
  const pausar=()=>{{pausado=true;anterior=0;if(reactivar)clearTimeout(reactivar);}};
  const reanudar=()=>{{if(reactivar)clearTimeout(reactivar);reactivar=setTimeout(()=>{{pausado=false;anterior=0;}},450);}};
  track.addEventListener('pointerdown',pausar,{{passive:true}});
  window.addEventListener('pointerup',reanudar,{{passive:true}});
  window.addEventListener('pointercancel',reanudar,{{passive:true}});
  track.addEventListener('touchstart',pausar,{{passive:true}});
  track.addEventListener('touchend',reanudar,{{passive:true}});
  track.addEventListener('touchcancel',reanudar,{{passive:true}});
  track.addEventListener('wheel',()=>{{pausar();reanudar();}},{{passive:true}});
  track.addEventListener('mouseenter',pausar,{{passive:true}});
  track.addEventListener('mouseleave',reanudar,{{passive:true}});
  track.addEventListener('focusin',pausar);
  track.addEventListener('focusout',reanudar);
  window.addEventListener('blur',()=>{{pausado=false;anterior=0;}});
  document.addEventListener('visibilitychange',()=>{{anterior=0;if(document.hidden)pausado=true;else pausado=false;}});
  function mover(t){{
   if(!anterior)anterior=t;
   const delta=Math.min(Math.max((t-anterior)/1000,0),0.05);anterior=t;
   const limite=maximo();
   if(!pausado&&limite>3){{
    const actual=track.scrollLeft;
    if(Math.abs(actual-ultimoScroll)>1)direccion=actual>ultimoScroll?1:-1;
    let siguiente=actual+direccion*velocidad*delta;
    if(siguiente>=limite){{siguiente=limite;direccion=-1;}}
    else if(siguiente<=0){{siguiente=0;direccion=1;}}
    track.scrollLeft=siguiente;
   }}
   ultimoScroll=track.scrollLeft;
   requestAnimationFrame(mover);
  }}
  requestAnimationFrame(mover);
 }});
}})();
</script>
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
    foto = f'<figure class="foto-marco"><img class="foto" src="{imagen}" alt="{titulo}" loading="lazy"></figure>' if imagen else ""
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
    referencias = [f"<li>{escapar(fuente.get('nombre', 'Fuente consultada'))}</li>" for fuente in noticia.get("fuentes", [])]
    cuerpo = f"""
    <main class="articulo">
      <div class="articulo-cabecera">
       <a class="volver" href="../index.html">← Volver a la portada</a>
       <p class="etiqueta">{categoria}</p>
       <h1>{titulo}</h1>
       <p class="bajada">{resumen}</p>
       <p class="fecha">Publicado: {escapar(noticia.get("fecha", fecha_actual()))} · Por CEV NOTICIAS</p>
       {etiqueta_estado(noticia)}
       {f'<p class="aviso-desarrollo">La información disponible es preliminar y puede cambiar. Se actualizará cuando existan nuevos datos confirmados por fuentes confiables.</p>' if noticia.get("estado_informacion") in ("en_desarrollo", "informacion_preliminar") else ""}
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




def crear_pagina_institucional(noticias):
    contenido = """
    <main class="pagina-editorial">
      <div class="sobrelinea">Conoce nuestro medio</div>
      <h1>Información con contexto.</h1>
      <p class="entradilla">CEV NOTICIAS es el espacio informativo de Cali en Vivo. Reunimos actualidad de Cali, el Valle del Cauca, Colombia y el mundo con una prioridad: contar qué se sabe, de dónde viene la información y qué sigue en desarrollo.</p>
      <div class="editorial-grid">
        <section class="editorial-card">
          <h2>Qué hacemos</h2>
          <p>Publicamos información de interés público en distintas áreas: ciudad, región, país, mundo, economía, deportes y tecnología. Cada noticia se presenta con un titular, un resumen y el contexto disponible.</p>
        </section>
        <section class="editorial-card">
          <h2>Criterios editoriales</h2>
          <ul>
            <li>Separar los hechos conocidos de las versiones iniciales.</li>
            <li>Atribuir la información a las fuentes consultadas.</li>
            <li>No presentar rumores como hechos ni completar vacíos con suposiciones.</li>
            <li>Actualizar las publicaciones cuando existan datos nuevos respaldados.</li>
          </ul>
        </section>
        <section class="editorial-card">
          <h2>Cómo leer los estados</h2>
          <p><strong>Actualidad:</strong> noticia publicada que no tiene una marca explícita de seguimiento.</p>
          <p><strong>Confirmada:</strong> los datos centrales están respaldados por las fuentes consultadas.</p>
          <p><strong>En desarrollo:</strong> el hecho sigue evolucionando y algunos datos pueden cambiar.</p>
          <p><strong>Información preliminar:</strong> se trata de un primer reporte o de datos que todavía requieren confirmación.</p>
        </section>
        <section class="editorial-card">
          <h2>Fuentes y correcciones</h2>
          <p>Las fuentes consultadas se muestran al final de cada artículo. Si encuentras un dato que deba revisarse, una actualización relevante o un error, puedes comunicarlo al equipo editorial para su evaluación.</p>
          <p><a class="leer" href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Contactar a CEV NOTICIAS por Instagram ↗</a></p>
        </section>
      </div>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/institucional.html"><meta property="og:type" content="website"><meta property="og:title" content="Quiénes somos | CEV NOTICIAS"><meta property="og:description" content="Conoce el propósito, los criterios editoriales y los estados informativos de CEV NOTICIAS."><meta name="robots" content="index,follow">'
    pagina = plantilla("Quiénes somos", contenido, "Conoce CEV NOTICIAS, sus criterios editoriales, sus fuentes y cómo identificar la información preliminar.", extra_head=extra)
    (SITE / "institucional.html").write_text(pagina, encoding="utf-8")


def crear_pagina_boletin(noticias):
    elementos = []
    for noticia in noticias[:10]:
        ident = escapar(noticia.get("id"))
        titulo = escapar(noticia.get("titulo"))
        resumen = escapar(noticia.get("resumen"))
        fecha = escapar(noticia.get("fecha", ""))
        categoria = escapar(noticia.get("categoria", "Actualidad"))
        elementos.append(
            f'<article class="boletin-item"><div class="fecha">{fecha}</div>'
            f'<div><span class="etiqueta">{categoria}</span>{etiqueta_estado(noticia)}'
            f'<h2><a href="notas/{ident}.html">{titulo}</a></h2><p>{resumen}</p></div></article>'
        )
    listado = "".join(elementos) if elementos else '<p class="vacio">El boletín se actualizará cuando haya noticias disponibles.</p>'
    contenido = f"""
    <main class="pagina-editorial">
      <div class="sobrelinea">Boletín informativo</div>
      <h1>Lo esencial, sin perder el contexto.</h1>
      <p class="entradilla">Una selección de las noticias más recientes publicadas por CEV NOTICIAS. Este resumen se actualiza junto con la edición digital para que puedas ponerte al día en un solo lugar.</p>
      <span class="boletin-fecha">Actualizado · {fecha_actual()}</span>
      <section class="boletin-lista" aria-label="Últimas noticias del boletín">{listado}</section>
      <div class="boletin-cta"><div><strong>¿Tienes una noticia o una corrección?</strong><p>Comparte información de interés y sugerencias con el equipo de CEV NOTICIAS.</p></div><a href="https://www.instagram.com/cev.noticias/" target="_blank" rel="noopener noreferrer">Escribir al medio ↗</a></div>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/boletin.html"><meta property="og:type" content="website"><meta property="og:title" content="Boletín de noticias | CEV NOTICIAS"><meta property="og:description" content="Consulta el resumen de las noticias más recientes de CEV NOTICIAS."><meta name="robots" content="index,follow">'
    pagina = plantilla("Boletín de noticias", contenido, "Resumen actualizado de las noticias publicadas por CEV NOTICIAS.", extra_head=extra)
    (SITE / "boletin.html").write_text(pagina, encoding="utf-8")



def crear_mapa_sitio(noticias):
    categorias = []
    for seccion in SECCIONES:
        if any(n.get("categoria") == seccion for n in noticias):
            categorias.append(f'<li><a href="https://cevnoticias.com/#categoria-{slug(seccion)}">{escapar(seccion)}</a></li>')
    articulos = "".join(
        f'<li><a href="notas/{escapar(n.get("id"))}.html">{escapar(n.get("titulo"))}</a><small>{escapar(n.get("categoria"))} · {escapar(n.get("fecha", ""))}</small></li>'
        for n in noticias
    )
    contenido = f"""
    <main class="pagina-editorial mapa-sitio">
      <div class="sobrelinea">Navegación</div><h1>Mapa del sitio</h1>
      <p class="entradilla">Encuentra las secciones, páginas y noticias publicadas en CEV NOTICIAS.</p>
      <div class="editorial-grid">
        <section class="editorial-card"><h2>Páginas principales</h2><ul><li><a href="https://cevnoticias.com/">Portada</a></li><li><a href="institucional.html">Quiénes somos</a></li><li><a href="boletin.html">Boletín de noticias</a></li></ul></section>
        <section class="editorial-card"><h2>Secciones con noticias</h2><ul>{''.join(categorias)}</ul></section>
        <section class="editorial-card mapa-articulos"><h2>Artículos publicados</h2><ul>{articulos}</ul></section>
      </div>
    </main>"""
    extra = '<link rel="canonical" href="https://cevnoticias.com/mapa-del-sitio.html"><meta property="og:type" content="website"><meta property="og:title" content="Mapa del sitio | CEV NOTICIAS"><meta property="og:description" content="Navega por las secciones y noticias de CEV NOTICIAS.">'
    pagina = plantilla("Mapa del sitio", contenido, "Mapa de secciones, páginas y noticias publicadas por CEV NOTICIAS.", extra_head=extra)
    (SITE / "mapa-del-sitio.html").write_text(pagina, encoding="utf-8")


def construir():
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])
    validas = []
    vistos = set()
    titulos_vistos = set()
    for noticia in noticias:
        titulo = str(noticia.get("titulo", "")).strip()
        contenido = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")
        if not titulo or len(contenido) < 250 or categoria not in SECCIONES or not imagen_segura(noticia.get("imagen")):
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
    
    for noticia in validas:
        crear_articulo(noticia, validas)

    SITE.mkdir(parents=True, exist_ok=True)
    crear_pagina_institucional(validas)
    crear_pagina_boletin(validas)
    crear_mapa_sitio(validas)
    principal = validas[0] if validas else None
    laterales = validas[1:4]
    if principal:
        imagen = imagen_segura(principal.get("imagen"))
        visual = f'<img src="{imagen}" alt="{escapar(principal.get("titulo"))}" fetchpriority="high">' if imagen else '<div class="imagen-vacia">CEV</div>'
        principal_html = f"""
        <article class="destacada" id="categoria-{slug(principal.get('categoria', ''))}">
         <a href="notas/{escapar(principal['id'])}.html">
          <div class="destacada-visual">{visual}</div>
          <div class="destacada-texto">
           <span class="etiqueta">Noticia central · {escapar(principal['categoria'])}</span>
           {etiqueta_estado(principal)}
           <h1>{escapar(principal['titulo'])}</h1>
           <p>{escapar(principal['resumen'])}</p>
           <div class="meta-noticia">{escapar(principal.get('fecha', fecha_actual()))}</div>
           <span class="boton">Leer noticia completa <span>↗</span></span>
          </div>
         </a>
        </article>"""
    else:
        principal_html = '<div class="vacio">Estamos preparando las próximas noticias. Vuelve pronto.</div>'

    conteos = {seccion: sum(1 for n in validas if n.get("categoria") == seccion) for seccion in SECCIONES}
    chips_seccion = "".join(
        f'<a class="explorar-chip" href="https://cevnoticias.com/#categoria-{slug(seccion)}"><span>{escapar(seccion)}</span><small>{conteos[seccion]}</small></a>'
        for seccion in SECCIONES if conteos[seccion]
    )
    lateral_html = f"""
    <aside class="lateral">
      <div class="lateral-kicker">CEV · GUÍA DE LECTURA</div>
      <h2 class="lateral-titulo">Explora por secciones</h2>
      <p class="lateral-intro">Accede directamente a los temas que te interesan.</p>
      <div class="explorar-secciones">{chips_seccion}</div>
      <div class="lateral-destino"><strong>Conoce nuestro medio</strong><p>Consulta quiénes somos y cómo trabajamos la información.</p><a href="institucional.html">Nuestra línea editorial ↗</a></div>
      <div class="lateral-destino lateral-boletin"><strong>Boletín de noticias</strong><p>Un resumen de las publicaciones más recientes.</p><a href="boletin.html">Ver el boletín ↗</a></div>
    </aside>"""
    portada = f'<section class="portada-grid">{principal_html}{lateral_html}</section>'

    excluidas = {principal["id"]} if principal else set()
    resto = [n for n in validas if n["id"] not in excluidas]
    categorias_ancladas = {principal.get("categoria")} if principal else set()
    tarjetas_lista = []
    for indice, noticia in enumerate(resto):
        categoria_noticia = noticia.get("categoria", "")
        ancla = ""
        if categoria_noticia not in categorias_ancladas:
            ancla = f'<span class="ancla-seccion" id="categoria-{slug(categoria_noticia)}" aria-hidden="true"></span>'
            categorias_ancladas.add(categoria_noticia)
        tarjetas_lista.append(ancla + tarjeta(noticia, indice))
    tarjetas = "".join(tarjetas_lista)
    feed = (
        f'<section class="bloque-categoria feed-noticias" id="ultimas-noticias"><h2 class="titulo-seccion">Últimas noticias</h2><div class="rejilla carrusel-infinito">{tarjetas}</div></section>'
        if resto else
        '<section class="bloque-categoria" id="ultimas-noticias"><h2 class="titulo-seccion">Últimas noticias</h2><p class="vacio">Próximamente encontrarás nuevas publicaciones.</p></section>'
    )
    contenido = f'<main class="contenedor"><div class="cinta"><span>Primera plana</span><a class="cinta-enlace" href="#ultimas-noticias">Ver últimas noticias <span aria-hidden="true">↘</span></a></div>{portada}{feed}</main>'
    datos_portada = {"@context":"https://schema.org","@type":"NewsMediaOrganization","name":"CEV NOTICIAS","url":"https://cevnoticias.com/","sameAs":["https://www.instagram.com/cev.noticias/"],"description":"Noticias de Cali, Valle del Cauca, Colombia y el mundo."}
    portada_head = '<link rel="canonical" href="https://cevnoticias.com/"><meta property="og:type" content="website"><meta property="og:title" content="CEV NOTICIAS | Actualidad y periodismo"><meta property="og:description" content="Noticias de Cali, Valle del Cauca, Colombia y el mundo."><meta name="twitter:card" content="summary_large_image">' + '<script type="application/ld+json">' + json.dumps(datos_portada, ensure_ascii=False) + '</script>'
    (SITE / "index.html").write_text(plantilla("Portada", contenido, "Noticias de Cali, Valle del Cauca, Colombia y el mundo.", extra_head=portada_head), encoding="utf-8")
    urls = ["https://cevnoticias.com/", "https://cevnoticias.com/institucional.html", "https://cevnoticias.com/boletin.html", "https://cevnoticias.com/mapa-del-sitio.html"] + [f"https://cevnoticias.com/notas/{n['id']}.html" for n in validas]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n' + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f'<url><loc>{html.escape(url)}</loc></url>\n' for url in urls) + '</urlset>\n'
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://cevnoticias.com/sitemap.xml\n", encoding="utf-8")
    print(f"Portada creada. Artículos publicados: {len(validas)}")


if __name__ == "__main__":
    construir()
