
import json
import os
import re
import html
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

BASE = Path(__file__).parent
SITE = BASE / "site"
NOTAS = SITE / "notas"
CACHE = BASE / "cache.json"

SECCIONES = [
    "Cali",
    "Valle del Cauca",
    "Colombia",
    "Internacional",
    "Deportes",
    "Tecnología",
    "Economía"
]

COLOMBIA_TZ = timezone(timedelta(hours=-5))


def escapar(valor):
    return html.escape(str(valor or ""), quote=True)


def cargar_json(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return defecto


def guardar_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)


def slug(texto):
    texto = str(texto).lower()
    reemplazos = {
        "á": "a", "é": "e", "í": "i",
        "ó": "o", "ú": "u", "ñ": "n"
    }
    for original, nuevo in reemplazos.items():
        texto = texto.replace(original, nuevo)
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-")[:75]


def fecha_actual():
    return datetime.now(COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p")


def imagen_segura(url):
    url = str(url or "").strip()
    if url.startswith("https://") or url.startswith("http://"):
        return escapar(url)
    return ""


def tarjeta(noticia):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    imagen = imagen_segura(noticia.get("imagen"))
    identificador = escapar(noticia.get("id"))

    if imagen:
        visual = f'<img src="{imagen}" alt="{titulo}" loading="lazy">'
    else:
        visual = '<div class="imagen-vacia">CEV NOTICIAS</div>'

    return f"""
    <article class="tarjeta">
        <a class="tarjeta-enlace" href="notas/{identificador}.html">
            <div class="tarjeta-imagen">{visual}</div>
            <div class="tarjeta-contenido">
                <span class="etiqueta">{categoria}</span>
                <h3>{titulo}</h3>
                <p>{resumen}</p>
                <span class="leer">Leer noticia completa →</span>
            </div>
        </a>
    </article>
    """


def plantilla(titulo, contenido, descripcion="CEV NOTICIAS"):
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{escapar(descripcion)}">
<title>{escapar(titulo)} | CEV NOTICIAS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
 --azul:#10283f; --rojo:#c83b35; --fondo:#f4f2ee;
 --texto:#202b35; --gris:#68737c; --blanco:#fff;
}}
* {{box-sizing:border-box}}
body {{margin:0;background:var(--fondo);color:var(--texto);font-family:'DM Sans',Arial,sans-serif}}
a {{color:inherit;text-decoration:none}}
.masthead {{background:var(--azul);color:white}}
.cabecera {{max-width:1200px;margin:auto;padding:27px 22px 20px}}
.marca {{font-family:'Playfair Display',serif;font-size:clamp(34px,6vw,58px);font-weight:800;letter-spacing:-2px}}
.marca span {{color:#e35b51}}
.eslogan {{color:#c9d4dc;font-size:12px;letter-spacing:2px;text-transform:uppercase;margin-top:5px}}
.fecha {{font-size:12px;color:#d4dce2;margin-top:17px}}
nav {{background:#0b1e30;border-top:1px solid #344657;overflow-x:auto}}
.nav-interior {{max-width:1200px;margin:auto;display:flex;gap:27px;padding:14px 22px;white-space:nowrap}}
nav a {{color:white;font-size:13px;font-weight:600}}
nav a:hover {{color:#f17b70}}
.contenedor {{max-width:1200px;margin:30px auto;padding:0 22px}}
.titulo-seccion {{font-family:'Playfair Display',serif;font-size:29px;margin:35px 0 17px}}
.destacada {{display:grid;grid-template-columns:1.4fr 1fr;background:white;border-radius:12px;overflow:hidden;box-shadow:0 5px 25px #14283c12}}
.destacada img {{width:100%;height:100%;min-height:300px;object-fit:cover}}
.destacada .imagen-vacia {{min-height:300px;display:grid;place-items:center;background:#dce4e8;color:#536575;font-weight:bold}}
.destacada-texto {{padding:30px;align-self:center}}
.destacada h2 {{font-family:'Playfair Display',serif;font-size:clamp(25px,3vw,38px);line-height:1.15;margin:12px 0}}
.etiqueta {{color:var(--rojo);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px}}
.destacada p,.tarjeta p {{color:var(--gris);line-height:1.65;font-size:14px}}
.boton {{display:inline-block;background:var(--rojo);color:white;padding:12px 17px;border-radius:5px;font-weight:700;font-size:13px;margin-top:8px}}
.rejilla {{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}}
.tarjeta {{background:white;border-radius:10px;overflow:hidden;box-shadow:0 3px 15px #14283c0c;transition:transform .2s}}
.tarjeta:hover {{transform:translateY(-3px)}}
.tarjeta-imagen {{height:190px;background:#dce4e8}}
.tarjeta-imagen img {{width:100%;height:100%;object-fit:cover}}
.imagen-vacia {{height:100%;display:grid;place-items:center;background:linear-gradient(135deg,#dbe3e8,#b9c9d2);color:#42566a;font-family:'Playfair Display',serif;font-size:20px}}
.tarjeta-contenido {{padding:19px}}
.tarjeta h3 {{font-family:'Playfair Display',serif;font-size:21px;line-height:1.25;margin:9px 0}}
.leer {{font-size:12px;color:var(--rojo);font-weight:700}}
.articulo {{max-width:850px;margin:35px auto;background:white;padding:clamp(22px,5vw,55px);border-radius:10px}}
.articulo h1 {{font-family:'Playfair Display',serif;font-size:clamp(32px,5vw,48px);line-height:1.12}}
.articulo .bajada {{font-size:19px;color:var(--gris);line-height:1.6}}
.articulo .foto {{width:100%;max-height:490px;object-fit:cover;border-radius:8px;margin:20px 0}}
.articulo .cuerpo {{font-size:17px;line-height:1.85;white-space:pre-line}}
.articulo .cuerpo p {{margin:0 0 20px}}
.fuentes {{border-top:1px solid #ddd;margin-top:35px;padding-top:20px;font-size:13px;color:var(--gris)}}
.pie {{margin-top:55px;background:var(--azul);color:white;padding:35px 22px;text-align:center}}
.pie strong {{font-family:'Playfair Display',serif;font-size:25px}}
.pie p {{color:#c9d4dc;font-size:12px}}
.vacio {{background:white;padding:25px;border-radius:8px;color:var(--gris)}}
@media(max-width:800px) {{
 .destacada {{grid-template-columns:1fr}}
 .destacada img {{min-height:220px;max-height:280px}}
 .rejilla {{grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}
 .tarjeta-imagen {{height:145px}}
 .tarjeta-contenido {{padding:13px}}
 .tarjeta h3 {{font-size:18px}}
}}
@media(max-width:480px) {{
 .rejilla {{grid-template-columns:1fr}}
 .tarjeta-imagen {{height:200px}}
 .contenedor {{padding:0 14px}}
}}
</style>
</head>
<body>
<header class="masthead">
 <div class="cabecera">
  <div class="marca">CEV <span>NOTICIAS</span></div>
  <div class="eslogan">Información · Actualidad · Periodismo</div>
  <div class="fecha">{fecha_actual()} · Colombia</div>
 </div>
  <nav><div class="nav-interior">
  <a href="/noti/">Inicio</a>
  {''.join(f'<a href="/noti/#{quote(s)}">{escapar(s)}</a>' for s in SECCIONES)}
 </div></nav>
</header>
{contenido}
<footer class="pie">
 <strong>CEV NOTICIAS</strong>
 <p>Información organizada para nuestros lectores.</p>
 <p>Las fuentes consultadas se identifican al final de cada artículo.</p>
</footer>
</body>
</html>"""


def crear_articulo(noticia):
    identificador = noticia["id"]
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    contenido = str(noticia.get("contenido") or "").strip()
    imagen = imagen_segura(noticia.get("imagen"))

    if imagen:
        foto = f'<img class="foto" src="{imagen}" alt="{titulo}">'
    else:
        foto = ""

    parrafos = "".join(
        f"<p>{escapar(p.strip())}</p>"
        for p in contenido.split("\n\n") if p.strip()
    )

    referencias = []

    for fuente in noticia.get("fuentes", []):
        nombre = escapar(fuente.get("nombre", "Fuente consultada"))
        referencias.append(f"<li>{nombre}</li>")

    cuerpo = f"""
    <main class="articulo">
      <a class="leer" href="../index.html">← Volver a CEV NOTICIAS</a>
      <p class="etiqueta">{categoria}</p>
      <h1>{titulo}</h1>
      <p class="bajada">{resumen}</p>
      <p class="fecha">Publicado: {escapar(noticia.get("fecha", fecha_actual()))}</p>
      {foto}
      <div class="cuerpo">{parrafos}</div>
      <div class="fuentes">
        <strong>Fuentes consultadas</strong>
        <ul>{''.join(referencias)}</ul>
        <p>Artículo de elaboración propia. Las fuentes se presentan para consulta y contraste.</p>
      </div>
    </main>
    """

    pagina = plantilla(titulo, cuerpo, resumen)
    NOTAS.mkdir(parents=True, exist_ok=True)
    (NOTAS / f"{identificador}.html").write_text(pagina, encoding="utf-8")


def construir():
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])

    # Cada noticia debe tener contenido suficiente y una categoría válida.
    validas = []
    vistos = set()

    for noticia in noticias:
        titulo = str(noticia.get("titulo", "")).strip()
        contenido = str(noticia.get("contenido", "")).strip()
        categoria = noticia.get("categoria", "")

        if not titulo or len(contenido) < 250:
            continue
        if categoria not in SECCIONES:
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
        visual = (
            f'<img src="{imagen}" alt="{escapar(destacada.get("titulo"))}">'
            if imagen else '<div class="imagen-vacia">CEV NOTICIAS</div>'
        )

        hero = f"""
        <section class="destacada">
          {visual}
          <div class="destacada-texto">
            <span class="etiqueta">Noticia destacada · {escapar(destacada["categoria"])}</span>
            <h2>{escapar(destacada["titulo"])}</h2>
            <p>{escapar(destacada["resumen"])}</p>
            <a class="boton" href="notas/{escapar(destacada["id"])}.html">Leer artículo</a>
          </div>
        </section>
        """
    else:
        hero = '<div class="vacio">Estamos preparando las próximas noticias. Vuelve pronto.</div>'

    bloques = []

    for seccion in SECCIONES:
        grupo = [
            n for n in validas
            if n["categoria"] == seccion and n is not destacada
        ]

        if not grupo:
            continue

        bloques.append(
            f'<section id="{quote(seccion)}">'
            f'<h2 class="titulo-seccion">{escapar(seccion)}</h2>'
            f'<div class="rejilla">{"".join(tarjeta(n) for n in grupo)}</div>'
            f'</section>'
        )

    contenido = f"""
    <main class="contenedor">
      <h2 class="titulo-seccion">La actualidad, en un solo lugar</h2>
      {hero}
      {''.join(bloques)}
    </main>
    """

    (SITE / "index.html").write_text(
        plantilla("Portada", contenido), encoding="utf-8"
    )

    print(f"Portada creada. Artículos publicados: {len(validas)}")


if __name__ == "__main__":
    construir()
