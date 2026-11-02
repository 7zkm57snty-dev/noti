import json
import re
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).parent
SITE = BASE / "site"
NOTAS = SITE / "notas"
CACHE = BASE / "cache.json"

SECCIONES = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología", "Economía"]
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
          <h3>{titulo}</h3>
          <p>{resumen}</p>
          <span class="leer">Leer noticia <span aria-hidden="true">↗</span></span>
        </div>
      </a>
    </article>"""


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS", ruta_raiz=""):
    enlaces = "".join(
        f'<a href="{ruta_raiz}#categoria-{slug(s)}">{escapar(s)}</a>'
        for s in SECCIONES
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f7f6f2">
<meta name="description" content="{escapar(descripcion)}">
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
.cabecera-meta{{display:flex;justify-content:space-between;align-items:center;margin-top:22px;padding-top:11px;border-top:1px solid var(--tinta);font-size:11px;color:#555}}
.estado{{font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:var(--rojo)}}
nav{{border-top:1px solid var(--linea);border-bottom:1px solid var(--tinta);background:var(--papel)}}
.nav-interior{{max-width:var(--ancho);margin:auto;display:flex;justify-content:center;gap:clamp(15px,3vw,34px);padding:14px 22px;overflow-x:auto;white-space:nowrap}}
nav a{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px}}
nav a:hover,nav a:focus{{color:var(--rojo)}}
.contenedor{{max-width:var(--ancho);margin:0 auto;padding:0 28px}}
.cinta{{display:flex;align-items:center;gap:12px;margin:27px 0 18px;font-size:10px;font-weight:800;letter-spacing:1.7px;text-transform:uppercase}}
.cinta:after{{content:"";height:1px;background:var(--linea);flex:1}}
.cinta span{{color:var(--rojo)}}
.destacada{{display:grid;grid-template-columns:1.12fr .88fr;min-height:390px;border-bottom:1px solid var(--tinta);padding-bottom:27px;gap:34px}}
.destacada-visual{{min-height:350px;overflow:hidden;background:#e7e3dc}}
.destacada-visual img{{width:100%;height:100%;min-height:350px;max-height:490px;object-fit:cover;display:block}}
.destacada-visual .imagen-vacia{{min-height:350px}}
.destacada-texto{{align-self:center;padding:12px 10px 12px 0}}
.etiqueta{{display:inline-block;color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase}}
.destacada h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(34px,4.5vw,58px);line-height:1.04;letter-spacing:-1.5px;margin:15px 0}}
.destacada p{{font-size:15px;line-height:1.75;color:var(--suave);max-width:560px}}
.meta-noticia{{font-size:10px;color:#777;margin-top:22px;text-transform:uppercase;letter-spacing:.8px}}
.boton{{display:inline-flex;align-items:center;gap:14px;margin-top:18px;padding:12px 0;border-top:1px solid var(--tinta);border-bottom:1px solid var(--tinta);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px}}
.boton:hover{{color:var(--rojo);border-color:var(--rojo)}}
.bloque-categoria{{padding:30px 0 34px;border-bottom:1px solid var(--linea)}}
.titulo-seccion{{display:flex;align-items:baseline;gap:13px;margin:0 0 20px;font-family:'Playfair Display',Georgia,serif;font-size:clamp(25px,3vw,34px);letter-spacing:-.6px}}
.titulo-seccion:after{{content:"";height:1px;background:var(--linea);flex:1}}
.rejilla{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}}
.tarjeta{{min-width:0}}
.tarjeta-enlace{{display:block;height:100%}}
.tarjeta-imagen{{height:205px;overflow:hidden;background:#e7e3dc}}
.tarjeta-imagen img{{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s}}
.tarjeta:hover .tarjeta-imagen img{{transform:scale(1.035)}}
.imagen-vacia{{height:100%;min-height:150px;display:grid;place-items:center;background:linear-gradient(135deg,#e8e4dc,#d4d0c8);color:#6b6258;font-family:'Playfair Display',serif;font-size:30px;font-weight:800;letter-spacing:2px}}
.tarjeta-contenido{{padding:14px 0 4px}}
.tarjeta h3{{font-family:'Playfair Display',Georgia,serif;font-size:23px;line-height:1.16;letter-spacing:-.4px;margin:8px 0}}
.tarjeta p{{font-size:12px;line-height:1.65;color:var(--suave);margin:8px 0 12px}}
.leer{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo)}}
.tarjeta-principal{{grid-column:span 2;display:grid;grid-template-columns:1.15fr .85fr;gap:20px;border-right:1px solid var(--linea);padding-right:22px}}
.tarjeta-principal .tarjeta-imagen{{height:100%;min-height:235px}}
.tarjeta-principal h3{{font-size:clamp(25px,3vw,34px)}}
.tarjeta-principal .tarjeta-contenido{{align-self:center;padding:8px 12px 8px 0}}
.vacio{{padding:20px 0;color:var(--suave);font-size:13px;border-top:1px solid var(--linea)}}
.articulo{{max-width:900px;margin:36px auto 65px;padding:0 28px}}
.articulo-cabecera{{max-width:780px;margin:0 auto 25px}}
.volver{{display:inline-block;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:var(--rojo);margin-bottom:30px}}
.articulo h1{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(38px,6vw,66px);line-height:1.03;letter-spacing:-1.8px;margin:13px 0 18px}}
.articulo .bajada{{font-size:clamp(17px,2vw,21px);line-height:1.6;color:#555;margin:0}}
.articulo .fecha{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#777;margin:22px 0}}
.articulo .foto{{width:100%;max-height:560px;object-fit:cover;display:block;margin:25px 0 35px}}
.articulo .cuerpo{{max-width:740px;margin:auto;font-family:Georgia,serif;font-size:19px;line-height:1.9;color:#292929;white-space:pre-line}}
.articulo .cuerpo p{{margin:0 0 24px}}
.fuentes{{max-width:740px;margin:42px auto 0;padding-top:20px;border-top:1px solid var(--linea);font-size:12px;color:#666}}
.fuentes strong{{color:var(--tinta);text-transform:uppercase;letter-spacing:1px;font-size:10px}}
.fuentes li{{margin:8px 0}}
.pie{{margin-top:35px;background:#171717;color:#fff;padding:36px 22px;text-align:center}}
.pie strong{{font-family:'Playfair Display',Georgia,serif;font-size:30px;letter-spacing:-1px}}
.pie strong span{{color:#e14a50}}
.pie p{{color:#aaa;font-size:11px;line-height:1.7}}
@media(max-width:850px){{
 .destacada{{grid-template-columns:1fr;gap:18px}}
 .destacada-visual,.destacada-visual img{{min-height:260px;max-height:380px}}
 .destacada-texto{{padding:0 4px}}
 .rejilla{{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}
 .tarjeta-principal{{grid-column:span 2}}
}}
@media(max-width:560px){{
 .cabecera{{padding:22px 15px 15px}}
 .marca{{font-size:49px;letter-spacing:-2.5px}}
 .cabecera-meta{{font-size:9px}}
 .nav-interior{{justify-content:flex-start;padding:13px 15px}}
 .contenedor{{padding:0 16px}}
 .destacada-visual,.destacada-visual img{{min-height:215px}}
 .destacada h1{{font-size:37px}}
 .rejilla{{grid-template-columns:1fr;gap:23px}}
 .tarjeta-principal{{grid-column:auto;display:block;border-right:0;padding-right:0}}
 .tarjeta-principal .tarjeta-imagen{{height:220px;min-height:0}}
 .tarjeta-principal .tarjeta-contenido{{padding:14px 0}}
 .tarjeta-imagen{{height:215px}}
 .articulo{{padding:0 18px;margin-top:25px}}
 .articulo h1{{font-size:41px}}
 .articulo .cuerpo{{font-size:18px}}
}}
</style>
</head>
<body>
<header class="masthead">
 <div class="cabecera">
  <div class="marca">CEV <span>NOTICIAS</span></div>
  <div class="eslogan">Periodismo · Contexto · Actualidad</div>
  <div class="cabecera-meta"><span>{fecha_actual()} · COLOMBIA</span><span class="estado">Edición digital</span></div>
 </div>
 <nav aria-label="Secciones"><div class="nav-interior">
  <a href="{ruta_raiz}">Portada</a>{enlaces}
 </div></nav>
</header>
{contenido}
<footer class="pie">
 <strong>CEV <span>NOTICIAS</span></strong>
 <p>Información, contexto y actualidad.</p>
 <p>Las fuentes consultadas se identifican al final de cada artículo.</p>
</footer>
<script>
(function(){{
 function aplicarFiltro(){{
  const hash=decodeURIComponent(window.location.hash.slice(1));
  const categoria=hash.startsWith("categoria-")?hash.slice(10):"";
  const destacada=document.querySelector(".destacada");
  const secciones=document.querySelectorAll(".bloque-categoria");
  if(!categoria){{
   if(destacada)destacada.hidden=false;
   secciones.forEach(s=>s.hidden=false);
   return;
  }}
  if(destacada)destacada.hidden=destacada.dataset.categoria!==categoria;
  secciones.forEach(s=>s.hidden=s.dataset.seccion!==categoria);
 }}
 window.addEventListener("hashchange",aplicarFiltro);
 aplicarFiltro();
}})();
</script>
</body>
</html>"""


def crear_articulo(noticia):
    identificador = noticia["id"]
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    contenido = str(noticia.get("contenido") or "").strip()
    imagen = imagen_segura(noticia.get("imagen"))
    foto = f'<img class="foto" src="{imagen}" alt="{titulo}" loading="lazy">' if imagen else ""
    parrafos = "".join(f"<p>{escapar(p.strip())}</p>" for p in contenido.split("\n\n") if p.strip())
    referencias = [
        f"<li>{escapar(fuente.get('nombre', 'Fuente consultada'))}</li>"
        for fuente in noticia.get("fuentes", [])
    ]
    cuerpo = f"""
    <main class="articulo">
      <div class="articulo-cabecera">
       <a class="volver" href="../index.html">← Volver a la portada</a>
       <p class="etiqueta">{categoria}</p>
       <h1>{titulo}</h1>
       <p class="bajada">{resumen}</p>
       <p class="fecha">Publicado: {escapar(noticia.get("fecha", fecha_actual()))}</p>
      </div>
      {foto}
      <div class="cuerpo">{parrafos}</div>
      <div class="fuentes"><strong>Fuentes consultadas</strong><ul>{''.join(referencias)}</ul>
       <p>Artículo de elaboración propia. Las fuentes se presentan para consulta y contraste.</p>
      </div>
    </main>"""
    pagina = plantilla(titulo, cuerpo, resumen, ruta_raiz="../")
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"{identificador}.html").write_text(pagina, encoding="utf-8")


def construir():
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])
    validas = []
    vistos = set()
    for noticia in noticias:
        titulo = str(noticia.get("titulo", "")).strip()
        contenido = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")
        if not titulo or len(contenido) < 250 or categoria not in SECCIONES:
            continue
        identificador = noticia.get("id") or slug(titulo)
        if identificador in vistos:
            continue
        noticia["id"] = identificador
        noticia.setdefault("fecha", fecha_actual())
        noticia.setdefault("resumen", contenido[:220])
        noticia.setdefault("fuentes", [])
        vistos.add(identificador)
        validas.append(noticia)
        crear_articulo(noticia)

    SITE.mkdir(parents=True, exist_ok=True)
    destacada = validas[0] if validas else None
    if destacada:
        imagen = imagen_segura(destacada.get("imagen"))
        visual = f'<img src="{imagen}" alt="{escapar(destacada.get("titulo"))}" fetchpriority="high">' if imagen else '<div class="imagen-vacia">CEV</div>'
        hero = f"""
        <section class="destacada" data-categoria="{slug(destacada['categoria'])}">
         <div class="destacada-visual">{visual}</div>
         <div class="destacada-texto">
          <span class="etiqueta">En portada · {escapar(destacada['categoria'])}</span>
          <h1>{escapar(destacada['titulo'])}</h1>
          <p>{escapar(destacada['resumen'])}</p>
          <div class="meta-noticia">{escapar(destacada.get('fecha', fecha_actual()))}</div>
          <a class="boton" href="notas/{escapar(destacada['id'])}.html">Leer historia completa <span>↗</span></a>
         </div>
        </section>"""
    else:
        hero = '<div class="vacio">Estamos preparando las próximas noticias. Vuelve pronto.</div>'

    bloques = []
    for seccion in SECCIONES:
        grupo = [n for n in validas if n["categoria"] == seccion and n is not destacada]
        if grupo:
            tarjetas = "".join(tarjeta(n, i) for i, n in enumerate(grupo))
            contenido_seccion = f'<div class="rejilla">{tarjetas}</div>'
        else:
            contenido_seccion = '<div class="vacio">Aún no hay noticias publicadas en esta categoría.</div>'
        bloques.append(
            f'<section id="categoria-{slug(seccion)}" class="bloque-categoria" data-seccion="{slug(seccion)}">'
            f'<h2 class="titulo-seccion">{escapar(seccion)}</h2>{contenido_seccion}</section>'
        )

    contenido = f'<main class="contenedor"><div class="cinta"><span>Última hora</span> · Las noticias que importan</div>{hero}{"".join(bloques)}</main>'
    (SITE / "index.html").write_text(plantilla("Portada", contenido), encoding="utf-8")
    print(f"Portada creada. Artículos publicados: {len(validas)}")


if __name__ == "__main__":
    construir()
