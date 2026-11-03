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
ASSETS_IA = BASE / "assets" / "imagenes-ia"
ARCHIVOS_ILUSTRACIONES_IA = ("sismo.svg", "infraestructura.svg", "espacio-publico.svg", "salud.svg", "gobierno.svg", "tecnologia.svg", "ciclismo.svg", "cafe-comercio.svg", "movilidad.svg")
MAX_TITULARES_PUBLICOS = 60
MAX_EDAD_TITULARES_PUBLICOS_HORAS = 72
MAX_BREVES_PUBLICOS = 8
MAX_EDAD_BREVES_HORAS = 120
HORAS_ETIQUETA_ULTIMA_HORA = 8

SECCIONES = ["Cali", "Valle del Cauca", "Colombia", "Internacional", "Deportes", "Tecnología", "Economía", "Tendencias", "Humor y opinión"]
ALCANCES_BREVES_PUBLICOS = {"Cali", "Valle del Cauca", "Colombia"}
COLOMBIA_TZ = timezone(timedelta(hours=-5))
IMAGENES_PROCESADAS = {}
FOTOS_RESPALDO_USADAS = set()
BIBLIOTECA_FOTOS = BASE / "biblioteca_fotos.json"


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
        # Segundo nivel: repositorios abiertos con licencia compatible.
        try:
            from imagenes import buscar_imagen
            resultado = buscar_imagen(
                noticia.get("titulo", ""),
                noticia.get("resumen", ""),
                noticia.get("categoria", "")
            )
            if resultado and resultado.get("url"):
                noticia["imagen"] = resultado["url"]
                noticia["imagen_credito"] = resultado
                url = resultado["url"]
        except Exception as error:
            print(f"No fue posible consultar repositorios externos: {error}")
    if not url.startswith(("https://", "http://")):
        respaldo = imagen_respaldo_categoria(noticia, identificador)
        IMAGENES_PROCESADAS[identificador] = respaldo
        return respaldo

    host = (urlsplit(url).hostname or "").lower()
    if host in ("cevnoticias.com", "www.cevnoticias.com"):
        url = ""

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
        print(f"Foto original no disponible para {identificador}; se consultarán repositorios: {error}")
        try:
            from imagenes import buscar_imagen
            resultado = buscar_imagen(noticia.get("titulo", ""), noticia.get("resumen", ""), noticia.get("categoria", ""))
            if resultado and resultado.get("url"):
                noticia["imagen"] = resultado["url"]
                noticia["imagen_credito"] = resultado
                return foto_local_noticia(noticia)
        except Exception as error_repositorio:
            print(f"Repositorios externos no disponibles: {error_repositorio}")
        respaldo = imagen_respaldo_categoria(noticia, identificador)
        IMAGENES_PROCESADAS[identificador] = respaldo
        return respaldo


def imagen_respaldo_categoria(noticia, identificador):
    """Usa fotografías reales almacenadas por categoría; nunca crea huecos visuales."""
    biblioteca = cargar_json(BIBLIOTECA_FOTOS, {"categorias": {}})
    categorias = biblioteca.get("categorias", {}) if isinstance(biblioteca, dict) else {}
    categoria = str(noticia.get("categoria") or "").strip()
    candidatos = categorias.get(categoria, []) or categorias.get("General", [])
    if not candidatos:
        candidatos = categorias.get("General", [])
    disponibles = [x for x in candidatos if isinstance(x, dict)]
    # Prioriza fotos no repetidas; si se agotan, permite reutilizar una de la categoría
    # antes que dejar una tarjeta sin imagen.
    ordenados = [x for x in disponibles if str(BASE / str(x.get("archivo") or "")) not in FOTOS_RESPALDO_USADAS]
    ordenados += [x for x in disponibles if x not in ordenados]
    for item in ordenados:
        ruta = BASE / str(item.get("archivo") or "")
        if not ruta.is_file():
            continue
        clave = str(ruta)
        FOTOS_RESPALDO_USADAS.add(clave)
        destino = SITE / "imagenes" / "biblioteca" / ruta.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, destino)
        noticia["imagen_credito"] = {
            "tipo": "imagen de referencia · fotografía de archivo",
            "fuente": item.get("fuente", "Wikimedia Commons"),
            "autor": item.get("autor", "Autor no identificado"),
            "pagina": item.get("pagina", ""),
            "licencia": item.get("licencia", ""),
            "licencia_url": item.get("licencia_url", "")
        }
        print(f"Fotografía de respaldo por categoría {categoria}: {ruta.name}")
        return f"/imagenes/biblioteca/{ruta.name}"
    print(f"Sin fotografía de respaldo disponible para categoría: {categoria}")
    return ""


def seleccionar_ilustracion_ia(noticia):
    """Selecciona un dibujo editorial conceptual, según el tema de la noticia."""
    texto = " ".join(str(noticia.get(campo, "")) for campo in ("titulo", "resumen", "texto", "contenido", "categoria")).lower()
    if re.search(r"bajo (los )?puentes|espacios publicos|parques|zonas verdes", texto):
        return "espacio-publico.svg"
    if re.search(r"demolicion|edificacion|edificios|infraestructura|megaproyectos|construccion|obras publicas", texto):
        return "infraestructura.svg"
    if re.search(r"sismo|terremoto|temblor|chaparral", texto):
        return "sismo.svg"
    if re.search(r"malaria|salud|hospital|paciente|virus|epidemia|enfermedad", texto):
        return "salud.svg"
    if re.search(r"ley de|congreso|camara|senado|legislativ|proyecto de ley", texto):
        return "gobierno.svg"
    if re.search(r"inteligencia artificial|\\bia\\b|tecnolog|spacex|anthropic|openai|marketing digital|centro de datos|software", texto):
        return "tecnologia.svg"
    if re.search(r"giro de rigo|ciclista|ciclismo|deporte|deportiv|atleta|carrera", texto):
        return "ciclismo.svg"
    if re.search(r"cafe|caficult|productores|agricultur|cultivo|cosecha|grano|economia|ingresos|ventas|tienda|comercio|negocio|emprend", texto):
        return "cafe-comercio.svg"
    if re.search(r"movilidad|transito|trafico|vehiculo|comparendo|caravana|transporte|vial", texto):
        return "movilidad.svg"

    categoria = str(noticia.get("categoria", "")).lower()
    if categoria == "deportes":
        return "ciclismo.svg"
    if categoria in ("economía", "economia", "valle del cauca"):
        return "cafe-comercio.svg"
    if categoria == "cali":
        return "movilidad.svg"
    if categoria == "colombia":
        return "gobierno.svg"
    if categoria == "tecnología":
        return "tecnologia.svg"
    return "espacio-publico.svg"


def copiar_ilustraciones_ia():
    """Copia las ilustraciones SVG editoriales al sitio estático."""
    if not ASSETS_IA.is_dir():
        print("No se encontró el directorio de ilustraciones; se mantiene el modo sin fotografía.")
        return
    destino = SITE / "imagenes-ia"
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in ARCHIVOS_ILUSTRACIONES_IA:
        origen = ASSETS_IA / nombre
        if origen.is_file():
            shutil.copy2(origen, destino / nombre)
    print("Ilustraciones editoriales SVG copiadas al sitio.")


def imagen_noticia(noticia, alt="", clase="", loading="lazy", prioridad=False):
    """Muestra únicamente fotografías reales con licencia y atribución verificadas.

    Si no hay una fotografía editorial válida, deja el espacio sin imagen:
    nunca sustituye el hecho por una ilustración sintética genérica.
    """
    fotografia = foto_local_noticia(noticia)
    if fotografia:
        credito = noticia.get("imagen_credito") or {}
        clases_base = [clase, "imagen-editorial"]
        if clase == "foto" and str(credito.get("tipo", "")).lower().startswith("retrato"):
            clases_base.append("foto-retrato")
        clases = " ".join(parte for parte in clases_base if parte)
        clase_html = f' class="{escapar(clases)}"' if clases else ""
        prioridad_html = ' fetchpriority="high"' if prioridad else ""
        return (
            f'<img{clase_html} src="{fotografia}" alt="{escapar(alt)}" '
            f'loading="{escapar(loading)}" decoding="async"{prioridad_html}>'
        )

    return ""


def tiempo_relativo_html(noticia, fecha_fallback=""):
    """Marca temporal que el navegador recalcula en cada carga de la página."""
    fecha_iso = fecha_schema(noticia)
    if not fecha_iso:
        return f'<span class="tiempo-absoluto">{escapar(fecha_fallback)}</span>' if fecha_fallback else ""
    return (
        f'<time class="tiempo-relativo" datetime="{escapar(fecha_iso)}" '
        f'title="{escapar(fecha_fallback)}">{escapar(fecha_fallback or "Publicado recientemente")}</time>'
    )


def tarjeta(noticia, posicion=0, ruta_raiz=""):
    titulo = escapar(noticia.get("titulo"))
    resumen = escapar(noticia.get("resumen"))
    categoria = escapar(noticia.get("categoria"))
    identificador = escapar(noticia.get("id"))
    visual = imagen_noticia(noticia, alt=titulo)
    clase_sin_imagen = "" if visual else " tarjeta-sin-imagen"
    credito_visual = noticia.get("imagen_credito") or {}
    tipo_visual = str(credito_visual.get("tipo", "")).lower()
    sello_visual = '<span class="sello-foto">Imagen de referencia</span>' if tipo_visual.startswith("imagen de referencia") else ""
    bloque_imagen = f'<div class="tarjeta-imagen">{visual}{sello_visual}</div>' if visual else ""
    marca_tiempo = tiempo_relativo_html(noticia, str(noticia.get("fecha", "")))
    return f"""
    <article class="tarjeta tarjeta-vertical{clase_sin_imagen}">
      <a class="tarjeta-enlace" href="/notas/{identificador}.html">
        <div class="tarjeta-cabecera">
          {bloque_imagen}
          <div class="tarjeta-titular">
            <span class="etiqueta">{categoria}</span>
            <h3>{titulo}</h3>
          </div>
        </div>
        <div class="tarjeta-contenido">
          <p>{resumen}</p>
          <div class="meta-tarjeta">{marca_tiempo}</div>
          <span class="leer">Leer noticia <span aria-hidden="true">↗</span></span>
        </div>
      </a>
    </article>"""

def tarjeta_rss(titular):
    titulo = escapar(titular.get("titulo"))
    identificador = escapar(titular.get("id"))
    fuente = escapar(titular.get("fuente") or "Medio de origen")
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    marca_tiempo = tiempo_relativo_html(titular, fecha_texto)
    if not titulo or not identificador:
        return ""
    destino = f"/notas/actualidad-{identificador}.html"
    return f"""
    <article class="tarjeta tarjeta-vertical titular-externo">
      <a class="tarjeta-enlace titular-rss-enlace" href="{destino}">
        <div class="tarjeta-contenido">
          <span class="rss-sello">REDACCIÓN CEV NOTICIAS · FUENTE: {fuente}</span>
          <h3>{titulo}</h3>
          <div class="rss-datos"><span>Publicado originalmente · {marca_tiempo}</span></div>
          <span class="leer">Ver ficha y crédito de origen ↗</span>
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
    marca_tiempo = tiempo_relativo_html(item, fecha_texto)
    visual = imagen_noticia(item, alt=titulo)
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
          <small>{marca_tiempo}</small>
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
    """Filtra titulares recientes sin confundir el tope de resultados con la fecha mínima."""
    ahora = datetime.now(timezone.utc).timestamp()
    fecha_minima = ahora - MAX_EDAD_TITULARES_PUBLICOS_HORAS * 3600
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
        if not fecha or fecha < fecha_minima or fecha > ahora + 2 * 3600:
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
    if limite is None:
        return resultado
    return resultado[:max(0, int(limite))]


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


def seleccionar_breves_publicos(breves, noticias):
    """Muestra solo mini-noticias recientes, revisadas y con crédito de fuente verificable."""
    ahora = datetime.now(timezone.utc).timestamp()
    limite = ahora - MAX_EDAD_BREVES_HORAS * 3600
    resultado = []
    vistos = set()
    for original in breves if isinstance(breves, list) else []:
        if not isinstance(original, dict):
            continue
        breve = dict(original)
        titulo = str(breve.get("titulo") or "").strip()
        texto = str(breve.get("texto") or "").strip()
        categoria = breve.get("categoria")
        ambito = breve.get("ambito")
        fecha = fecha_ordenable(breve)
        fuentes = breve.get("fuentes", [])
        fuentes_validas = [
            f for f in fuentes
            if isinstance(f, dict)
            and str(f.get("nombre", "")).strip()
            and str(f.get("titulo", "")).strip()
            and urlsplit(str(f.get("url", "")).strip()).scheme == "https"
            and urlsplit(str(f.get("url", "")).strip()).hostname
        ] if isinstance(fuentes, list) else []
        palabras = len(texto.split())
        if (
            not titulo
            or categoria not in SECCIONES
            or categoria == "Internacional"
            or ambito not in ALCANCES_BREVES_PUBLICOS
            or not 45 <= palabras <= 100
        ):
            continue
        if not fecha or fecha < limite or fecha > ahora + 2 * 3600 or not fuentes_validas:
            continue
        if titular_repite_articulo(titulo, noticias):
            continue
        clave = re.sub(r"[^a-z0-9]+", " ", titulo.lower()).strip()
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        breve["fuentes"] = fuentes_validas
        resultado.append(breve)
    resultado.sort(key=fecha_ordenable, reverse=True)
    return resultado[:MAX_BREVES_PUBLICOS]


def tarjeta_breve(breve):
    """Tarjeta editorial de texto; acredita los medios sin enlazar ni redirigir fuera del sitio."""
    titulo = escapar(breve.get("titulo"))
    texto = escapar(breve.get("texto"))
    categoria = escapar(breve.get("categoria"))
    ambito = escapar(breve.get("ambito"))
    fecha = fecha_ordenable(breve)
    ahora = datetime.now(timezone.utc).timestamp()
    es_ultima_hora = bool(fecha and 0 <= ahora - fecha <= HORAS_ETIQUETA_ULTIMA_HORA * 3600)
    etiqueta = "ÚLTIMA HORA" if es_ultima_hora else "LO MÁS DESTACADO"
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m · %I:%M %p") if fecha else ""
    marca_tiempo = tiempo_relativo_html(breve, fecha_texto)
    visual = imagen_noticia(breve, alt=titulo, clase="breve-foto")
    credito_visual = breve.get("imagen_credito") or {}
    tipo_visual = str(credito_visual.get("tipo", "")).lower()
    sello_visual = '<span class="sello-foto">Imagen de referencia</span>' if tipo_visual.startswith("imagen de referencia") else ""
    bloque_visual = f'<div class="breve-imagen">{visual}{sello_visual}</div>' if visual else ""
    autor_visual = escapar(credito_visual.get("autor", ""))
    fuente_visual = escapar(credito_visual.get("fuente", ""))
    pagina_visual = imagen_segura(credito_visual.get("pagina", ""))
    licencia_visual = imagen_segura(credito_visual.get("licencia_url", ""))
    enlaces_visual = []
    if pagina_visual:
        enlaces_visual.append(f'<a href="{pagina_visual}" target="_blank" rel="noopener noreferrer">fuente de imagen</a>')
    if licencia_visual:
        enlaces_visual.append(f'<a href="{licencia_visual}" target="_blank" rel="noopener noreferrer">licencia</a>')
    credito_visual_html = (
        f'<p class="credito-imagen-mini">Imagen: {autor_visual} · {fuente_visual} {" · ".join(enlaces_visual)}</p>'
        if autor_visual or fuente_visual else ""
    )
    nombres = []
    for fuente in breve.get("fuentes", []):
        nombre = str(fuente.get("nombre", "")).strip()
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    credito = escapar(", ".join(nombres))
    return f"""
    <article class="breve-actualidad">
      {bloque_visual}
      {credito_visual_html}
      <div class="breve-etiquetas">
        <span class="breve-estado">{etiqueta}</span>
        <span class="breve-categoria">{ambito} · {categoria}</span>
      </div>
      <h3>{titulo}</h3>
      <p class="breve-texto">{texto}</p>
      <div class="breve-pie">
        <span>Redacción CEV NOTICIAS</span>
        <span>Fuentes: {credito}</span>
        {marca_tiempo}
      </div>
    </article>"""


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
<meta name="theme-color" content="#17212b">
<meta name="description" content="{escapar(descripcion)}">
{extra_head}
<title>{escapar(titulo)} | CEV NOTICIAS</title>
<!-- Tipografías del sistema: no se contactan proveedores externos antes del consentimiento. -->
<style>
:root{{--papel:#edf1f5;--blanco:#fff;--tinta:#17212b;--suave:#5e6975;--linea:#d9e0e7;--rojo:#b5282f;--ancho:1280px}}
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
.nav-carrusel{{width:100%;max-width:760px;margin:0 auto;padding:0 18px;display:grid;grid-template-columns:34px minmax(0,1fr) 34px;gap:10px;align-items:center}}
.nav-interior{{display:flex;width:100%;min-width:0;max-width:100%;margin:0;flex-flow:row nowrap;align-items:center;justify-content:flex-start;gap:8px;padding:9px 2px;overflow-x:scroll;overflow-y:hidden;white-space:nowrap;scrollbar-width:none;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scroll-behavior:auto;scroll-snap-type:none;touch-action:pan-x;}}
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
.bloque-investigacion{{max-width:780px;margin:28px auto;padding:18px 20px;border-left:3px solid var(--rojo);background:#efece6;font-size:13px;line-height:1.65}}
.bloque-investigacion strong{{display:block;margin-bottom:7px;text-transform:uppercase;letter-spacing:1px;font-size:10px}}
.bloque-investigacion p{{margin:6px 0}}
.bloque-investigacion ul{{margin:8px 0 0;padding-left:20px}}
body.noche .bloque-investigacion{{background:#262322;color:#eee}}
.bloque-breves{{margin:34px 0 42px;padding:24px;background:var(--blanco);border:1px solid var(--linea);border-radius:16px}}
.breves-encabezado{{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:20px}}
.breves-encabezado .etiqueta{{margin:0 0 7px;color:var(--rojo);font-size:10px;font-weight:800;letter-spacing:1.5px}}
.breves-encabezado h2{{margin:0;font-family:Georgia,serif;font-size:clamp(24px,3vw,34px);letter-spacing:-.5px}}
.breves-encabezado p{{margin:8px 0 0;color:var(--suave);font-size:13px;line-height:1.55;max-width:660px}}
.breves-encabezado .contador-noticias{{white-space:nowrap}}
.breves-actualizacion{{display:block;margin-top:7px;color:var(--suave);font-size:10px;letter-spacing:.2px}}
.breves-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.breve-actualidad{{min-width:0;padding:17px 17px 15px;border:1px solid var(--linea);border-radius:12px;background:#fbfaf7;display:flex;flex-direction:column;gap:10px}}
.breve-etiquetas{{display:flex;flex-wrap:wrap;align-items:center;gap:7px}}
.breve-estado{{padding:4px 7px;background:#b5282f;color:#fff;border-radius:4px;font-size:9px;font-weight:800;letter-spacing:.7px}}
.breve-categoria{{color:var(--suave);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.7px}}
.breve-actualidad h3{{margin:0;font-size:17px;line-height:1.3;letter-spacing:-.2px}}
.breve-texto{{margin:0;color:#383838;font-size:13px;line-height:1.65}}
.breve-pie{{margin-top:auto;padding-top:11px;border-top:1px solid var(--linea);display:flex;flex-direction:column;gap:4px;color:var(--suave);font-size:10px;line-height:1.45}}
.breve-pie span:first-child{{color:var(--tinta);font-weight:800}}
.breve-pie time{{font-variant-numeric:tabular-nums}}
body.noche .bloque-breves{{background:#191919;border-color:#444}}
body.noche .breve-actualidad{{background:#222;border-color:#444}}
body.noche .breve-texto{{color:#ddd}}
@media(max-width:900px){{.breves-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:600px){{.bloque-breves{{padding:16px;margin:22px 0 30px}}.breves-grid{{grid-template-columns:1fr}}.breves-encabezado{{align-items:flex-start;flex-direction:column}}}}
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

/* Indicadores compactos superiores: TRM oficial y condiciones actuales de Cali. */
.franja-indicadores{{max-width:1360px;margin:0 auto;padding:12px clamp(16px,3.2vw,42px);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:12px;align-items:center;background:#f5f7fa;border-bottom:1px solid #dce3e9}}
.indicador-dato{{min-width:0;display:flex;align-items:center;gap:11px;padding:8px 12px;background:#fff;border:1px solid #e0e6ec;border-radius:10px}}
.indicador-icono{{width:36px;height:36px;flex:none;border-radius:9px;display:grid;place-items:center;background:#eef2f6;color:#17212b;font-size:14px;font-weight:900}}
.indicador-texto{{min-width:0;display:flex;flex-direction:column;gap:2px}}
.indicador-texto small{{font-size:8px;font-weight:900;letter-spacing:1.1px;text-transform:uppercase;color:#697887}}
.indicador-texto strong{{font-size:16px;line-height:1.1;color:#17212b;font-variant-numeric:tabular-nums}}
.indicador-texto span{{font-size:9px;color:#667482;line-height:1.35}}
.fuentes-indicadores{{display:flex;flex-direction:column;gap:4px;align-items:flex-end;font-size:8px;color:#657483;text-align:right;line-height:1.4}}
.fuentes-indicadores a{{text-decoration:underline;text-underline-offset:2px}}
.fuentes-indicadores a:hover{{color:#b5282f}}
.indicador-error{{color:#a5222a!important}}
.meta-tarjeta{{margin-top:8px;font-size:10px;color:#687786}}
.tiempo-relativo{{font-variant-numeric:tabular-nums;white-space:nowrap}}
.visual-ia{{position:relative;display:block;width:100%;height:100%;min-height:120px;background-color:#dfe6ed;background-repeat:no-repeat;overflow:hidden;border-radius:inherit}}
.visual-ia .imagen-ia-img{{display:block;width:100%;height:100%;min-height:0;object-fit:cover;border-radius:inherit}}
.visual-ia .sello-imagen-ia{{position:absolute;z-index:2;right:8px;bottom:8px;padding:4px 7px;border-radius:4px;background:rgba(15,29,42,.72);color:#fff;font-size:7px;font-weight:800;letter-spacing:.45px;text-transform:uppercase;pointer-events:none}}
.tarjeta-imagen .visual-ia{{min-height:100%;height:100%}}
.destacada-visual .visual-ia{{min-height:0;height:100%}}
.express-foto .visual-ia{{min-height:0;height:100%}}
.breve-imagen{{height:auto;aspect-ratio:16/9;overflow:hidden;border-radius:9px;background:#e3e9ef}}
.breve-imagen .visual-ia{{min-height:0;height:100%}}
.breve-foto{{height:100%;min-height:0}}
.articulo .visual-ia.foto{{width:100%;height:auto;min-height:0;aspect-ratio:16/9;max-height:600px;margin:25px 0 8px;border-radius:13px}}
.articulo .visual-ia.foto .sello-imagen-ia{{font-size:9px;padding:6px 9px}}
.copyright{{margin:20px auto 0;padding-top:14px;max-width:760px;border-top:1px solid #41505d;color:#b8c3cd;font-size:10px;letter-spacing:.25px}}
@media(max-width:760px){{
 .franja-indicadores{{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px;padding:9px 12px}}
 .indicador-dato{{gap:8px;padding:8px}}
 .indicador-icono{{width:30px;height:30px;font-size:12px}}
 .indicador-texto small{{font-size:7px;letter-spacing:.7px}}
 .indicador-texto strong{{font-size:14px}}
 .indicador-texto span{{font-size:8px}}
 .fuentes-indicadores{{grid-column:1/-1;flex-direction:row;justify-content:space-between;align-items:center;gap:7px;font-size:8px;text-align:left}}
}}
@media(max-width:390px){{
 .franja-indicadores{{padding:8px 9px;gap:6px}}
 .indicador-dato{{padding:7px 6px;gap:6px}}
 .indicador-icono{{width:26px;height:26px;font-size:10px}}
 .indicador-texto small{{font-size:6px}}
 .indicador-texto strong{{font-size:13px}}
 .indicador-texto span{{font-size:7px}}
}}

@media(max-width:600px){{
 .cev-cookie-banner{{left:10px;bottom:10px;width:calc(100vw - 20px);padding:15px}}
 .cev-cookie-actions{{display:grid;grid-template-columns:1fr}}
 .cev-cookie-actions button{{width:100%}}
}}

/* ------------------------------------------------------------------
   CEV NOTICIAS · SISTEMA EDITORIAL MULTIDISPOSITIVO
   Una sola identidad visual para escritorio, tablet y celular.
------------------------------------------------------------------- */
body{{background:#e7ecf1;color:#17212b}}
.masthead{{background:#17212b;color:#f8fafc;box-shadow:0 5px 22px rgba(10,22,34,.16)}}
.cabecera{{padding:30px 32px 21px;text-align:center}}
.marca,.marca a{{color:#fff}}
.marca{{font-size:clamp(48px,6.2vw,78px);letter-spacing:-3px}}
.marca span{{color:#f06b70}}
.eslogan{{color:#d4dce4;letter-spacing:3.2px}}
.instagram-marca{{color:#f8fafc}}
.instagram-marca small{{color:#c5d0da}}
.instagram-marca svg{{color:#ff777d}}
.cabecera-meta{{border-top-color:#526171;color:#d4dce4}}
.estado{{color:#ff858a}}
nav{{background:#1d2a36;border-top:1px solid #354555;border-bottom:1px solid #354555}}
.nav-carrusel{{max-width:1280px;padding:0 24px;grid-template-columns:36px minmax(0,1fr) 36px;gap:12px}}
.nav-interior{{justify-content:center;gap:5px;padding:10px 2px}}
.nav-interior a{{color:#edf2f6;border-radius:7px 7px 0 0;padding:12px 13px}}
.nav-interior a.nav-activa{{color:#fff;background:#71343a;border-bottom-color:#ff858a}}
.nav-flecha{{width:36px;height:36px;border-color:#536475;color:#f8fafc}}
.nav-flecha:hover:not(:disabled){{background:#344555;border-color:#ff858a;color:#ff858a}}
nav a:hover,nav a:focus{{color:#ff9a9e}}
.barra-herramientas{{max-width:1280px;padding:13px 32px 16px;border:0;background:#243341}}
.buscador{{border:1px solid #536475;background:#f8fafc;color:#17212b;border-radius:8px;padding:12px 15px}}
.buscador::placeholder{{color:#697887}}
.accion-ui{{border:1px solid #83909d;border-radius:8px;background:transparent;color:#f8fafc;padding:12px 16px}}
.accion-ui:hover{{background:#f8fafc;color:#17212b;border-color:#f8fafc}}
.express-modulo{{max-width:1280px;margin:24px auto 18px;padding:0 28px}}
.express-cabecera{{padding:0 0 12px}}
.express-escenario{{border:1px solid #d9e0e7;border-radius:14px;overflow:hidden;box-shadow:0 6px 18px rgba(23,33,43,.06)}}
.express-enlace{{padding:18px}}
.contenedor{{max-width:1280px;margin:0 auto 28px;padding:8px 32px 42px;background:#f8fafc;border:1px solid #dfe5eb;border-top:0;border-radius:0 0 18px 18px;box-shadow:0 12px 34px rgba(23,33,43,.07)}}
.cinta{{margin:24px 0 18px}}
.portada-grid{{display:block;padding:22px;background:#fff;border:1px solid #dce3e9;border-radius:16px;box-shadow:0 8px 24px rgba(23,33,43,.06)}}
.destacada{{min-width:0}}
.destacada > a{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(300px,.9fr);gap:30px;align-items:center}}
.destacada-visual{{height:390px;min-height:0;border-radius:12px;background:#dce3e9}}
.destacada-texto{{padding:12px 8px 12px 0}}
.destacada h1{{font-size:clamp(34px,3.4vw,50px);line-height:1.06;letter-spacing:-1.35px;color:#17212b}}
.destacada p{{font-size:15px;line-height:1.75;color:#5b6875}}
.destacada .etiqueta{{color:#a5222a}}
.meta-noticia{{color:#697887}}
.boton{{border-color:#b5282f;color:#a5222a}}
.lateral{{border-color:#d9e0e7}}
.relevante{{border-bottom-color:#e1e6eb}}
.relevante h3{{color:#1b2936}}
.bloque-breves{{margin:28px 0 34px;padding:26px;background:#f8e9eb;border:1px solid #eed1d5;border-radius:16px}}
.breves-encabezado{{margin-bottom:18px}}
.breves-encabezado h2{{color:#17212b}}
.breves-grid{{gap:14px}}
.breve-actualidad{{background:#fff;border:1px solid #ead8db;border-radius:12px;box-shadow:0 4px 12px rgba(70,30,35,.045)}}
.breve-texto{{color:#344250}}
.breve-pie{{border-color:#ead8db}}
.breve-pie span:first-child{{color:#17212b}}
.bloque-categoria{{margin-top:24px;padding:26px;background:#edf1f5;border:1px solid #dce3e9;border-radius:16px}}
.titulo-seccion{{color:#17212b}}
.lista-noticias{{gap:14px;border:0}}
.tarjeta-vertical{{padding:14px;background:#fff;border:1px solid #dce3e9;border-radius:14px;box-shadow:0 4px 14px rgba(23,33,43,.045);transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}}
.tarjeta-vertical:hover{{transform:translateY(-2px);border-color:#bdc9d4;box-shadow:0 9px 22px rgba(23,33,43,.09)}}
.tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(230px,34%) minmax(0,1fr);gap:24px}}
.tarjeta-vertical .tarjeta-imagen{{height:205px;border-radius:10px;background:#e4e9ee}}
.tarjeta-vertical .tarjeta-imagen img{{border-radius:10px}}
.tarjeta-vertical .tarjeta-contenido{{padding:5px 4px}}
.tarjeta-vertical h3{{color:#17212b;font-size:clamp(22px,2.15vw,30px);line-height:1.14}}
.tarjeta-vertical p{{color:#596775;font-size:13px}}
.tarjeta-vertical .etiqueta{{color:#a5222a}}
.tarjeta-sin-imagen .tarjeta-enlace{{grid-template-columns:minmax(0,1fr)}}
.tarjeta-sin-imagen .tarjeta-contenido{{padding:10px 8px}}
.vacio{{padding:22px;background:#fff;border:1px dashed #cbd4dd;border-radius:10px}}
.articulo{{max-width:980px;margin:34px auto 62px;padding:38px 54px 54px;background:#fff;border:1px solid #dce3e9;border-radius:18px;box-shadow:0 10px 30px rgba(23,33,43,.07)}}
.articulo-cabecera{{max-width:820px}}
.articulo h1{{color:#17212b;line-height:1.05}}
.articulo .bajada{{color:#526171}}
.articulo .fecha{{color:#75818c}}
.articulo .foto{{width:100%;max-height:600px;aspect-ratio:16/9;object-fit:cover;border-radius:14px;margin:28px 0 10px;background:#e7ecf1}}
.credito-imagen{{color:#697887}}
.articulo .cuerpo{{color:#273542;font-size:19px;line-height:1.88}}
.fuentes{{border-top:1px solid #dce3e9;color:#526171}}
.fuentes strong{{color:#17212b}}
.bloque-investigacion{{max-width:740px;margin:26px auto;padding:20px 22px;background:#edf2f6;border-left:4px solid #b5282f;border-radius:0 10px 10px 0;color:#273542}}
.relacionadas .tarjeta{{border:1px solid #dce3e9;border-radius:12px;box-shadow:0 4px 12px rgba(23,33,43,.04)}}
.pie{{margin-top:0;background:#17212b;border-top:5px solid #b5282f;padding:42px 22px}}
.pie strong span{{color:#ff777d}}
.pie-enlaces a{{text-decoration:none}}
.pie-enlaces a:hover{{color:#ff9a9e}}
body.noche{{background:#111820}}
body.noche .masthead{{background:#121d27}}
body.noche nav{{background:#182633}}
body.noche .contenedor{{background:#1a232c;border-color:#34414d}}
body.noche .buscador{{background:#eef2f6;color:#17212b}}
body.noche .portada-grid,body.noche .tarjeta-vertical,body.noche .express-escenario{{background:#222d37;border-color:#3b4854}}
body.noche .destacada h1,body.noche .relevante h3,body.noche .titulo-seccion,body.noche .breves-encabezado h2{{color:#f5f7f9}}
body.noche .destacada p,body.noche .tarjeta-vertical p,body.noche .relevante p{{color:#c3cdd6}}
body.noche .bloque-breves{{background:#302329;border-color:#65434a}}
body.noche .breve-actualidad{{background:#252e37;border-color:#49535e}}
body.noche .breve-texto{{color:#e2e7ec}}
body.noche .breve-pie{{border-color:#49535e}}
body.noche .breve-pie span:first-child{{color:#f5f7f9}}
body.noche .bloque-categoria{{background:#202a34;border-color:#394652}}
body.noche .articulo{{background:#202a34;border-color:#3b4854}}
body.noche .articulo h1,body.noche .fuentes strong{{color:#f5f7f9}}
body.noche .articulo .cuerpo{{color:#e8edf1}}
body.noche .bloque-investigacion{{background:#2a3540;color:#e8edf1}}
body.noche .vacio{{background:#222d37;border-color:#49535e}}
@media(max-width:900px){{
 .portada-grid{{padding:18px}}
 .destacada > a{{grid-template-columns:minmax(0,1fr) minmax(260px,.9fr);gap:20px}}
 .destacada-visual{{height:320px}}
 .tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(190px,36%) minmax(0,1fr);gap:18px}}
 .contenedor{{padding-left:22px;padding-right:22px}}
 .articulo{{margin-left:22px;margin-right:22px;padding:32px 34px 42px}}
}}
@media(max-width:700px){{
 .cabecera{{padding:23px 16px 17px}}
 .marca{{font-size:clamp(41px,11vw,52px);letter-spacing:-2.5px}}
 .eslogan{{font-size:9px;letter-spacing:2px}}
 .cabecera-meta{{margin-top:17px;font-size:9px}}
 .nav-carrusel{{padding:0 10px;grid-template-columns:30px minmax(0,1fr) 30px;gap:7px}}
 .nav-flecha{{width:30px;height:30px}}
 .nav-interior{{justify-content:flex-start;gap:5px;padding:8px 1px}}
 .nav-interior a{{padding:10px 11px;font-size:9px}}
 .barra-herramientas{{padding:11px 15px 14px;flex-wrap:wrap;gap:8px}}
 .buscador{{flex:1 1 100%;min-width:0}}
 .accion-ui{{flex:1 1 auto;padding:11px 12px}}
 .express-modulo{{padding:0 15px;margin:18px auto 14px}}
 .express-enlace{{grid-template-columns:112px minmax(0,1fr);gap:13px;padding:13px}}
 .express-foto{{height:112px}}
 .contenedor{{padding:8px 13px 26px;margin-bottom:18px;border-radius:0 0 13px 13px}}
 .cinta{{margin:17px 1px 13px;font-size:9px;letter-spacing:1.2px}}
 .portada-grid{{padding:12px;border-radius:13px}}
 .destacada > a{{grid-template-columns:minmax(0,1fr);gap:0}}
 .destacada-visual{{height:auto;aspect-ratio:16/9;border-radius:10px}}
 .destacada-texto{{padding:15px 3px 5px}}
 .destacada h1{{font-size:clamp(28px,8vw,36px);letter-spacing:-.8px}}
 .destacada p{{font-size:13px;line-height:1.65}}
 .bloque-breves{{margin:20px 0 24px;padding:17px 14px;border-radius:13px}}
 .breves-grid{{grid-template-columns:minmax(0,1fr);gap:11px}}
 .breve-actualidad{{padding:14px}}
 .bloque-categoria{{margin-top:18px;padding:18px 12px;border-radius:13px}}
 .titulo-seccion{{font-size:25px;gap:8px;line-height:1.15}}
 .tarjeta-vertical{{padding:11px;border-radius:12px}}
 .tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(0,1fr);gap:12px}}
 .tarjeta-vertical .tarjeta-imagen{{height:auto;aspect-ratio:16/9;border-radius:9px}}
 .tarjeta-vertical .tarjeta-imagen img{{border-radius:9px}}
 .tarjeta-vertical .tarjeta-contenido{{padding:3px 2px 5px}}
 .tarjeta-vertical h3{{font-size:23px;line-height:1.16}}
 .tarjeta-vertical p{{font-size:12px;line-height:1.6;margin:7px 0 10px}}
 .articulo{{margin:18px 12px 34px;padding:23px 18px 32px;border-radius:13px}}
 .articulo-cabecera{{margin-bottom:19px}}
 .articulo h1{{font-size:clamp(31px,9vw,40px);letter-spacing:-.9px;line-height:1.06}}
 .articulo .bajada{{font-size:16px;line-height:1.55}}
 .articulo .fecha{{font-size:9px;line-height:1.55}}
 .articulo .foto{{margin:20px 0 8px;border-radius:10px;max-height:none}}
 .articulo .cuerpo{{font-size:17px;line-height:1.78}}
 .articulo .cuerpo p{{margin-bottom:20px}}
 .bloque-investigacion{{padding:16px;margin:20px auto}}
 .fuentes{{margin-top:30px;font-size:11px;overflow-wrap:anywhere}}
 .relacionadas{{margin-top:34px}}
 .relacionadas .rejilla{{grid-template-columns:minmax(0,1fr)}}
 .pie{{padding:33px 17px}}
}}
@media(max-width:390px){{
 .cabecera-meta{{font-size:8px;letter-spacing:.2px}}
 .nav-carrusel{{padding:0 7px;gap:5px}}
 .nav-interior a{{padding:9px 9px;font-size:8px}}
 .marca{{font-size:41px}}
 .destacada h1{{font-size:29px}}
 .tarjeta-vertical h3{{font-size:21px}}
 .articulo{{margin-left:8px;margin-right:8px;padding:20px 15px 28px}}
 .articulo h1{{font-size:30px}}
}}
@media(prefers-reduced-motion:reduce){{
 *,*::before,*::after{{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
}}


/* CEV NOTICIAS · refinamiento editorial común para escritorio, tableta y móvil */
:root{{--papel:#eef2f6;--blanco:#fff;--tinta:#17212b;--suave:#596775;--linea:#dfe5eb;--rojo:#bd2632;--ancho:1320px}}
html,body{{max-width:100%;overflow-x:clip}}
body{{background:#eef2f6;color:#17212b;line-height:1.55}}
.masthead{{background:#17212b;color:#f8fafc;box-shadow:0 5px 24px rgba(10,22,34,.17)}}
.cabecera{{max-width:1360px;padding:30px clamp(16px,3.2vw,42px) 20px}}
.marca{{font-size:clamp(48px,6.2vw,80px);letter-spacing:-3.2px}}
.eslogan{{color:#d9e1e8}}
.cabecera-meta{{border-top-color:#526171;color:#d9e1e8}}
.estado{{color:#ff858a}}
nav{{background:#1d2a36;border-color:#354555}}
.nav-carrusel{{max-width:1360px;padding-inline:clamp(10px,2.4vw,32px)}}
.nav-interior a{{border-radius:7px 7px 0 0}}
.barra-herramientas{{max-width:1360px;padding:13px clamp(16px,3.2vw,42px) 16px;background:#243341}}
.buscador{{border-radius:9px;background:#fff;border-color:#647382}}
.accion-ui{{border-radius:9px}}
.express-modulo{{max-width:1360px}}
.contenedor{{max-width:1360px;padding:10px clamp(16px,3.2vw,42px) 44px;background:#fff;border:1px solid #dfe5eb;border-top:0;border-radius:0 0 20px 20px;box-shadow:0 12px 34px rgba(23,33,43,.07)}}
.cinta{{margin:25px 0 18px}}
.cinta span:first-child{{color:#bd2632}}
.portada-grid{{padding:clamp(18px,2.2vw,30px);background:#fff;border:1px solid #dce3e9;border-top:4px solid #bd2632;border-radius:16px;box-shadow:0 8px 24px rgba(23,33,43,.055)}}
.destacada > a{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:clamp(20px,2.6vw,34px);align-items:center}}
.destacada > a:has(.destacada-visual) .destacada-visual{{height:auto;min-height:0;aspect-ratio:16/9;max-height:440px;border-radius:12px;background:#dce3e9}}
.destacada-visual img{{border-radius:12px}}
.destacada-texto{{padding:8px 4px}}
.destacada h1{{font-size:clamp(32px,3.6vw,52px);line-height:1.06;letter-spacing:-1.3px;color:#17212b}}
.destacada p{{font-size:15px;line-height:1.75;color:#596775}}
.destacada .etiqueta,.tarjeta-vertical .etiqueta{{color:#a5222a}}
.meta-noticia{{color:#6b7783}}
.boton{{border-color:#bd2632;color:#a5222a}}
.relevante h3{{color:#17212b}}
.bloque-breves{{background:#fff1f2;border-color:#efd5d8}}
.breve-actualidad{{background:#fff;border-color:#ead8db}}
.bloque-categoria{{background:#f2f5f8;border-color:#e0e6ec}}
.titulo-seccion{{color:#17212b}}
.lista-noticias{{gap:14px;border:0}}
.tarjeta-vertical{{padding:15px;background:#fff;border:1px solid #e0e6ec;border-radius:13px;box-shadow:0 4px 14px rgba(23,33,43,.045);transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}}
.tarjeta-vertical:hover{{transform:translateY(-2px);border-color:#c5d0da;box-shadow:0 9px 22px rgba(23,33,43,.085)}}
.tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(220px,34%) minmax(0,1fr);gap:clamp(16px,2.2vw,28px)}}
.tarjeta-vertical .tarjeta-imagen{{height:auto;min-height:0;aspect-ratio:16/10;border-radius:9px;background:#e2e8ee}}
.tarjeta-vertical .tarjeta-imagen img{{border-radius:9px}}
.tarjeta-vertical .tarjeta-contenido{{padding:5px 7px}}
.tarjeta-vertical h3{{font-size:clamp(21px,2.1vw,30px);line-height:1.15;color:#17212b}}
.tarjeta-vertical p{{color:#596775;line-height:1.7}}
.articulo{{max-width:1020px;background:#fff;border:1px solid #dfe5eb;border-radius:18px;box-shadow:0 10px 32px rgba(23,33,43,.065)}}
.articulo h1{{color:#17212b}}
.articulo .bajada{{color:#536170}}
.articulo .cuerpo{{color:#263542}}
.articulo .foto{{border-radius:13px}}
.pie{{background:#17212b;border-top:5px solid #bd2632}}
/* La variante oscura manual sigue disponible y mantiene contraste legible. */
body.noche{{background:#111820;color:#f5f7f9}}
body.noche .masthead{{background:#121d27}}
body.noche nav{{background:#182633}}
body.noche .contenedor{{background:#1a232c;border-color:#34414d}}
body.noche .portada-grid,body.noche .tarjeta-vertical,body.noche .express-escenario{{background:#222d37;border-color:#3b4854}}
body.noche .bloque-categoria{{background:#202a34;border-color:#394652}}
body.noche .destacada h1,body.noche .relevante h3,body.noche .titulo-seccion,body.noche .breves-encabezado h2,body.noche .tarjeta-vertical h3{{color:#f5f7f9}}
body.noche .destacada p,body.noche .tarjeta-vertical p,body.noche .relevante p{{color:#c3cdd6}}
body.noche .articulo{{background:#202a34;border-color:#3b4854}}
body.noche .articulo h1,body.noche .fuentes strong{{color:#f5f7f9}}
body.noche .articulo .cuerpo{{color:#e8edf1}}
body.noche .bloque-breves{{background:#302329;border-color:#65434a}}
body.noche .breve-actualidad{{background:#252e37;border-color:#49535e}}
body.noche .breve-texto{{color:#e2e7ec}}
body.noche .breve-pie{{border-color:#49535e}}
@media(max-width:900px){{
 .contenedor{{padding-inline:22px}}
 .tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(190px,36%) minmax(0,1fr);gap:18px}}
 .articulo{{margin-inline:22px}}
}}
@media(max-width:700px){{
 .cabecera{{padding:21px 15px 16px}}
 .marca{{font-size:clamp(40px,10.8vw,53px);letter-spacing:-2.4px}}
 .eslogan{{font-size:9px;letter-spacing:1.8px}}
 .cabecera-meta{{margin-top:15px;padding-top:10px;font-size:9px;gap:8px}}
 .nav-carrusel{{padding:0 9px;grid-template-columns:28px minmax(0,1fr) 28px;gap:6px}}
 .nav-flecha{{width:28px;height:28px;font-size:18px}}
 .nav-interior{{justify-content:flex-start;gap:5px;padding:8px 1px}}
 .nav-interior a{{padding:10px 10px;font-size:9px}}
 .barra-herramientas{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding:10px 13px 13px}}
 .buscador{{width:100%;min-width:0;padding:11px 12px;font-size:12px}}
 .accion-ui{{white-space:nowrap;padding:10px 9px;font-size:9px}}
 .express-modulo{{padding:0 14px;margin:17px auto 13px}}
 .express-enlace{{grid-template-columns:108px minmax(0,1fr);gap:12px;padding:12px}}
 .express-foto{{height:auto;aspect-ratio:1/1}}
 .contenedor{{padding:8px 13px 25px;margin:0 0 17px;border-left:0;border-right:0;border-radius:0 0 13px 13px}}
 .cinta{{margin:16px 1px 12px;font-size:9px;letter-spacing:1px}}
 .portada-grid{{padding:12px;border-radius:13px}}
 .destacada > a{{grid-template-columns:minmax(0,1fr);gap:0}}
 .destacada > a:has(.destacada-visual) .destacada-visual{{height:auto;aspect-ratio:16/9;border-radius:9px}}
 .destacada-texto{{padding:13px 3px 5px}}
 .destacada h1{{font-size:clamp(28px,8vw,36px);letter-spacing:-.8px}}
 .destacada p{{font-size:13px;line-height:1.65}}
 .bloque-breves{{margin:18px 0 22px;padding:15px 13px;border-radius:13px}}
 .breves-grid{{grid-template-columns:minmax(0,1fr);gap:10px}}
 .breve-actualidad{{padding:13px}}
 .bloque-categoria{{margin-top:16px;padding:16px 11px;border-radius:13px}}
 .titulo-seccion{{font-size:24px;gap:7px;line-height:1.15}}
 .tarjeta-vertical{{padding:11px;border-radius:11px}}
 .tarjeta-vertical .tarjeta-enlace{{grid-template-columns:minmax(0,1fr);gap:10px}}
 .tarjeta-vertical .tarjeta-imagen{{height:auto;aspect-ratio:16/9;border-radius:8px}}
 .tarjeta-vertical .tarjeta-contenido{{padding:2px 2px 4px}}
 .tarjeta-vertical h3{{font-size:clamp(21px,6.4vw,24px)}}
 .tarjeta-vertical p{{font-size:12px;line-height:1.6;margin:7px 0 9px}}
 .articulo{{margin:16px 10px 30px;padding:21px 16px 29px;border-radius:13px}}
 .articulo h1{{font-size:clamp(30px,8.5vw,39px)}}
 .articulo .bajada{{font-size:16px}}
 .articulo .cuerpo{{font-size:17px;line-height:1.78}}
 .pie{{padding:31px 16px}}
}}
@media(max-width:390px){{
 .cabecera{{padding-inline:12px}}
 .marca{{font-size:40px}}
 .cabecera-meta{{font-size:8px;letter-spacing:.1px}}
 .nav-interior a{{padding:9px 8px;font-size:8px}}
 .barra-herramientas{{padding-inline:10px}}
 .accion-ui{{font-size:8px;padding-inline:7px}}
 .contenedor{{padding-inline:10px}}
 .destacada h1{{font-size:29px}}
 .tarjeta-vertical h3{{font-size:21px}}
 .articulo{{margin-inline:7px;padding-inline:14px}}
}}


/* Ajuste final de tarjetas: cabecera visual independiente y cuerpo alineado. */
.tarjeta-vertical .tarjeta-enlace{{
 display:block;
 min-width:0;
}}
.tarjeta-vertical .tarjeta-cabecera{{
 display:grid;
 grid-template-columns:minmax(210px,34%) minmax(0,1fr);
 gap:clamp(16px,2.2vw,27px);
 align-items:stretch;
 min-width:0;
}}
.tarjeta-vertical .tarjeta-imagen{{
 width:100%;
 height:auto;
 min-height:0;
 aspect-ratio:16/10;
 overflow:hidden;
 border-radius:11px;
 background:#e3e9ef;
}}
.tarjeta-vertical .tarjeta-imagen img,
.tarjeta-vertical .tarjeta-imagen .visual-ia,
.tarjeta-vertical .tarjeta-imagen .visual-ia-img{{
 display:block;
 width:100%;
 height:100%;
 min-height:0;
 object-fit:cover;
 border-radius:11px;
}}
.tarjeta-vertical .tarjeta-titular{{
 display:flex;
 min-width:0;
 flex-direction:column;
 justify-content:center;
 align-items:flex-start;
 padding:4px 0;
}}
.tarjeta-vertical .tarjeta-titular .etiqueta{{margin:0 0 8px}}
.tarjeta-vertical .tarjeta-titular h3{{
 margin:0;
 color:#17212b;
 font-size:clamp(22px,2.25vw,31px);
 line-height:1.14;
 letter-spacing:-.35px;
 overflow-wrap:break-word;
 hyphens:auto;
}}
.tarjeta-vertical .tarjeta-contenido{{
 display:block;
 min-width:0;
 padding:14px 0 3px;
}}
.tarjeta-vertical .tarjeta-contenido p{{
 max-width:none;
 margin:0 0 12px;
 font-size:13px;
 line-height:1.7;
 color:#596775;
 overflow-wrap:anywhere;
}}
.tarjeta-vertical .meta-tarjeta{{margin:0 0 8px;font-size:10px;color:#687786}}
.tarjeta-vertical .leer{{display:inline-block;margin-top:2px}}
.tarjeta-vertical.tarjeta-sin-imagen .tarjeta-cabecera{{grid-template-columns:minmax(0,1fr)}}
.tarjeta-vertical.tarjeta-sin-imagen .tarjeta-titular{{padding:3px 0}}
.tarjeta-vertical .tarjeta-imagen .visual-ia{{min-height:0;height:100%}}
.visual-ia .imagen-ia-img{{display:block;width:100%;height:100%;min-height:0;object-fit:cover}}
.breve-imagen{{width:100%;max-width:420px;aspect-ratio:16/9;height:auto;margin:0 0 12px;overflow:hidden;border-radius:10px;background:#e3e9ef}}
.breve-imagen .visual-ia{{width:100%;height:100%;min-height:0}}
.breve-imagen img,.breve-foto{{display:block;width:100%;height:100%;min-height:0;object-fit:cover}}
.articulo .foto{{width:100%;height:auto;max-height:560px;aspect-ratio:16/9;object-fit:cover;display:block}}
.articulo .visual-ia.foto{{display:block;width:100%;height:auto;min-height:0;aspect-ratio:16/9;max-height:560px;overflow:hidden;border-radius:13px}}
.articulo .visual-ia.foto .imagen-ia-img{{width:100%;height:100%;min-height:0;object-fit:cover}}
.visual-ia .sello-imagen-ia{{position:absolute;right:8px;bottom:8px;padding:4px 7px;border-radius:4px;background:rgba(15,29,42,.72);color:#fff;font-size:7px;font-weight:800;letter-spacing:.45px;pointer-events:none}}
@media(max-width:900px){{
 .tarjeta-vertical .tarjeta-cabecera{{grid-template-columns:minmax(180px,36%) minmax(0,1fr);gap:18px}}
}}
@media(max-width:700px){{
 .tarjeta-vertical .tarjeta-cabecera{{grid-template-columns:minmax(0,1fr);gap:12px}}
 .tarjeta-vertical .tarjeta-imagen{{aspect-ratio:16/9;max-height:none}}
 .tarjeta-vertical .tarjeta-titular{{justify-content:flex-start;padding:0}}
 .tarjeta-vertical .tarjeta-titular h3{{font-size:clamp(22px,6.4vw,26px);line-height:1.16}}
 .tarjeta-vertical .tarjeta-contenido{{padding:10px 0 2px}}
 .tarjeta-vertical .tarjeta-contenido p{{font-size:12px;line-height:1.62}}
 .breve-imagen{{max-width:none;aspect-ratio:16/9}}
}}

 
/* Créditos discretos y etiquetas de referencia sin alterar el encuadre. */
.tarjeta-imagen,.breve-imagen{{position:relative}}
.sello-foto{{position:absolute;z-index:3;left:8px;bottom:8px;padding:4px 7px;border-radius:4px;background:rgba(19,31,43,.72);color:#fff;font-size:8px;font-weight:700;letter-spacing:.25px;line-height:1.2;pointer-events:none}}
.credito-imagen-mini{{margin:4px 0 10px;color:#73808b;font-size:9px;line-height:1.4;overflow-wrap:anywhere}}
.credito-imagen-mini a{{color:inherit;text-decoration:underline;text-underline-offset:2px}}
.articulo .foto-retrato{{display:block;width:auto;height:auto;max-width:100%;max-height:640px;aspect-ratio:auto;object-fit:contain;margin:25px auto 8px}}
@media(max-width:700px){{.credito-imagen-mini{{font-size:8px}}}}

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
 <section class="franja-indicadores" aria-label="Indicadores del día">
   <div class="indicador-dato indicador-trm">
    <span class="indicador-icono" aria-hidden="true">USD</span>
    <div class="indicador-texto"><small>Dólar · TRM oficial</small><strong id="cev-trm-valor">Consultando…</strong><span id="cev-trm-vigencia">Superintendencia Financiera</span></div>
   </div>
   <div class="indicador-dato indicador-clima">
    <span class="indicador-icono" id="cev-clima-icono" aria-hidden="true">☁</span>
    <div class="indicador-texto"><small>Clima actual · Cali</small><strong id="cev-clima-valor">Consultando…</strong><span id="cev-clima-detalle">Condiciones meteorológicas</span></div>
   </div>
   <div class="fuentes-indicadores">
    <span>Datos de referencia · consulta automática cada 12 horas</span>
    <span><a href="https://www.datos.gov.co/Econom-a-y-Finanzas/Tasa-de-Cambio-Representativa-del-Mercado-TRM/32sa-8pi3" target="_blank" rel="noopener noreferrer">TRM: Superfinanciera</a> · <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Clima: Open-Meteo</a></span>
   </div>
  </section>
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
  <p class="copyright">Copyright © {datetime.now(COLOMBIA_TZ).year} CEV NOTICIAS · Todos los derechos reservados.</p>
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
   const hayDesbordamiento=maximo>4;
   if(navAnterior)navAnterior.disabled=!hayDesbordamiento||nav.scrollLeft<=2;
   if(navSiguiente)navSiguiente.disabled=!hayDesbordamiento||nav.scrollLeft>=maximo-2;
  }};
  const moverNav=(direccion)=>{{
   const maximo=maxScroll();
   if(maximo<=4){{actualizarNav();return;}}
   const paso=Math.max(200,Math.round(nav.clientWidth*0.8));
   const destino=Math.max(0,Math.min(maximo,nav.scrollLeft+(direccion*paso)));
   nav.scrollLeft=destino;
   actualizarNav();
   window.setTimeout(actualizarNav,80);
  }};
  navAnterior?.addEventListener('click',()=>moverNav(-1));
  navSiguiente?.addEventListener('click',()=>moverNav(1));
  nav.addEventListener('scroll',actualizarNav,{{passive:true}});
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
   nav.scrollLeft=Math.max(0,Math.min(maxScroll(),objetivo));
  }};
  const recalcular=()=>{{centrarActiva();actualizarNav();}};
  window.addEventListener('resize',recalcular);
  window.addEventListener('load',recalcular,{{once:true}});
  if('ResizeObserver' in window){{
   const observador=new ResizeObserver(recalcular);
   observador.observe(nav);
   if(nav.parentElement)observador.observe(nav.parentElement);
  }}
  requestAnimationFrame(recalcular);
  if(document.fonts?.ready)document.fonts.ready.then(recalcular);
 }}
 const barra=document.getElementById('progreso-lectura'),arriba=document.getElementById('volver-arriba');
 function actualizar(){{const max=document.documentElement.scrollHeight-window.innerHeight;if(barra)barra.style.width=(max>0?(window.scrollY/max)*100:0)+'%';if(arriba)arriba.hidden=window.scrollY<450;}}
 window.addEventListener('scroll',actualizar,{{passive:true}});actualizar();
 if(arriba)arriba.addEventListener('click',()=>window.scrollTo({{top:0,behavior:'smooth'}}));

 // Antigüedad editorial: se calcula con la fecha original y el reloj del visitante.
 function actualizarTiemposRelativos(){{
  const ahora=Date.now();
  document.querySelectorAll('time.tiempo-relativo[datetime]').forEach(el=>{{
   const instante=Date.parse(el.getAttribute('datetime')||'');
   if(!Number.isFinite(instante))return;
   const minutos=Math.floor((ahora-instante)/60000);
   if(minutos<0){{el.textContent='Programada';return;}}
   if(minutos<1){{el.textContent='Hace menos de un minuto';return;}}
   if(minutos<60){{el.textContent='Hace '+minutos+' '+(minutos===1?'minuto':'minutos');return;}}
   const horas=Math.floor(minutos/60);
   if(horas<24){{el.textContent='Hace '+horas+' '+(horas===1?'hora':'horas');return;}}
   const dias=Math.floor(horas/24);
   if(dias<7){{el.textContent='Hace '+dias+' '+(dias===1?'día':'días');return;}}
   const semanas=Math.floor(dias/7);
   if(semanas<5){{el.textContent='Hace '+semanas+' '+(semanas===1?'semana':'semanas');return;}}
   const meses=Math.floor(dias/30);
   if(meses<12){{el.textContent='Hace '+meses+' '+(meses===1?'mes':'meses');return;}}
   const anios=Math.floor(dias/365);
   el.textContent='Hace '+anios+' '+(anios===1?'año':'años');
  }});
 }}
 actualizarTiemposRelativos();
 window.setInterval(actualizarTiemposRelativos,60000);

 // Indicadores: TRM oficial y clima de Cali; ambos se consultan al cargar y cada 12 horas.
 const trmValor=document.getElementById('cev-trm-valor');
 const trmVigencia=document.getElementById('cev-trm-vigencia');
 const climaValor=document.getElementById('cev-clima-valor');
 const climaDetalle=document.getElementById('cev-clima-detalle');
 const climaIcono=document.getElementById('cev-clima-icono');
 async function cargarTRM(){{
  if(!trmValor)return;
  try{{
   const respuesta=await fetch('https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC',{{cache:'no-store'}});
   if(!respuesta.ok)throw new Error('TRM HTTP '+respuesta.status);
   const filas=await respuesta.json(),dato=Array.isArray(filas)?filas[0]:null;
   const valor=Number(dato?.valor);
   if(!dato||!Number.isFinite(valor)||valor<=0)throw new Error('La fuente no devolvió una tasa válida');
   trmValor.textContent=new Intl.NumberFormat('es-CO',{{style:'currency',currency:'COP',maximumFractionDigits:2}}).format(valor)+' por USD';
   const vigencia=dato.vigenciadesde?new Date(dato.vigenciadesde):null;
   trmVigencia.textContent=vigencia&&!Number.isNaN(vigencia.getTime())?'Vigencia: '+vigencia.toLocaleDateString('es-CO',{{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Bogota'}}):'Vigencia oficial más reciente';
   trmValor.classList.remove('indicador-error');
  }}catch(error){{
   trmValor.textContent='No disponible';
   trmVigencia.textContent='No se pudo consultar la fuente oficial';
   trmValor.classList.add('indicador-error');
  }}
 }}
 function textoClima(codigo){{
  if(codigo===0)return 'Despejado';
  if(codigo===1)return 'Mayormente despejado';
  if(codigo===2)return 'Parcialmente nublado';
  if(codigo===3)return 'Nublado';
  if(codigo===45||codigo===48)return 'Neblina';
  if([51,53,55,56,57].includes(codigo))return 'Llovizna';
  if([61,63,65,66,67,80,81,82].includes(codigo))return 'Lluvia';
  if([71,73,75,77,85,86].includes(codigo))return 'Nieve';
  if([95,96,99].includes(codigo))return 'Tormenta';
  return 'Condición variable';
 }}
 function iconoClima(codigo,dia){{
  if(codigo===0)return dia?'☀':'🌙';
  if([1,2,3].includes(codigo))return '⛅';
  if([45,48].includes(codigo))return '🌫';
  if([51,53,55,56,57,61,63,65,66,67,80,81,82].includes(codigo))return '🌧';
  if([71,73,75,77,85,86].includes(codigo))return '❄';
  if([95,96,99].includes(codigo))return '⛈';
  return '🌤';
 }}
 async function cargarClima(){{
  if(!climaValor)return;
  const url='https://api.open-meteo.com/v1/forecast?latitude=3.4516&longitude=-76.5320&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day&timezone=America%2FBogota';
  try{{
   const respuesta=await fetch(url,{{cache:'no-store'}});
   if(!respuesta.ok)throw new Error('Clima HTTP '+respuesta.status);
   const datos=await respuesta.json(),actual=datos.current||{{}};
   const temp=Number(actual.temperature_2m),sensacion=Number(actual.apparent_temperature),codigo=Number(actual.weather_code);
   if(!Number.isFinite(temp)||!Number.isFinite(codigo))throw new Error('El proveedor no devolvió condiciones válidas');
   climaValor.textContent=Math.round(temp)+' °C · '+textoClima(codigo);
   const partes=[];
   if(Number.isFinite(sensacion))partes.push('Sensación '+Math.round(sensacion)+' °C');
   if(Number.isFinite(Number(actual.relative_humidity_2m)))partes.push('Humedad '+Math.round(Number(actual.relative_humidity_2m))+'%');
   climaDetalle.textContent=partes.join(' · ')||'Condiciones actuales en Cali';
   climaIcono.textContent=iconoClima(codigo,Number(actual.is_day)!==0);
   climaValor.classList.remove('indicador-error');
  }}catch(error){{
   climaValor.textContent='No disponible';
   climaDetalle.textContent='No se pudo consultar el clima actual';
   climaIcono.textContent='—';
   climaValor.classList.add('indicador-error');
  }}
 }}
 cargarTRM();
 cargarClima();
 const intervaloIndicadores=12*60*60*1000;
 window.setInterval(cargarTRM,intervaloIndicadores);
 window.setInterval(cargarClima,intervaloIndicadores);

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
        tipo_imagen = escapar(credito.get("tipo", "Fotografía de archivo"))
        pagina_imagen = imagen_segura(credito.get("pagina", ""))
        licencia_url = imagen_segura(credito.get("licencia_url", ""))
        enlaces_credito = []
        if pagina_imagen:
            enlaces_credito.append(f'<a href="{pagina_imagen}" target="_blank" rel="noopener">fuente original</a>')
        if licencia_url:
            enlaces_credito.append(f'<a href="{licencia_url}" target="_blank" rel="noopener">licencia</a>')
        extras = " · ".join(enlaces_credito)
        atribucion_imagen = f'<p class="credito-imagen">{tipo_imagen}: {autor} · {origen} · {licencia} {extras}</p>'
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

    investigacion = noticia.get("investigacion") or {}
    enfoque = escapar(investigacion.get("enfoque_original", ""))
    hechos = investigacion.get("hechos_clave") or []
    hechos = [escapar(hecho) for hecho in hechos if str(hecho).strip()]
    bloque_investigacion = ""
    if enfoque or hechos:
        lista_hechos = "".join(f"<li>{hecho}</li>" for hecho in hechos[:5])
        bloque_investigacion = f"""
        <aside class="bloque-investigacion">
          <strong>Qué aporta esta cobertura</strong>
          {f'<p>{enfoque}</p>' if enfoque else ''}
          {f'<ul>{lista_hechos}</ul>' if lista_hechos else ''}
        </aside>"""

    cuerpo = f"""
    <main class="articulo">
      <div class="articulo-cabecera">
       <a class="volver" href="/">← Volver a la portada</a>
       <p class="etiqueta">{categoria}</p>
       <h1>{titulo}</h1>
       <p class="bajada">{resumen}</p>
       <p class="fecha">Publicado: {tiempo_relativo_html(noticia, str(noticia.get("fecha", fecha_actual())))} · Por <a href="../redaccion.html">Redacción CEV NOTICIAS</a></p>
       <p class="fecha">Fuentes consultadas: {len(noticia.get("fuentes", []))}</p>
      </div>
      {foto}
      {f'<p class="credito-imagen">Ilustración conceptual generada con IA; no corresponde a una fotografía documental del hecho.</p>' if foto and not imagen else ''}
      {atribucion_imagen}
      {bloque_investigacion}
      <div class="cuerpo">{parrafos}</div>
      <div class="fuentes"><strong>Fuentes consultadas</strong><ul>{''.join(referencias)}</ul>
       <p>Contenido elaborado por CEV NOTICIAS a partir de las fuentes identificadas. Consulta las publicaciones originales para ampliar la información y contrastar los datos.</p>
      </div>
      {bloque_relacionadas}
    </main>"""
    url_articulo = f"https://cevnoticias.com/notas/{identificador}.html"
    datos_schema = {"@context":"https://schema.org","@type":"NewsArticle","headline":str(noticia.get("titulo","")),"description":str(noticia.get("resumen","")),"author":{"@type":"Organization","name":"Redacción CEV NOTICIAS"},"publisher":{"@type":"Organization","name":"CEV NOTICIAS"},"mainEntityOfPage":url_articulo}
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
    # No reproducimos imágenes RSS sin poder comprobar que correspondan a esta noticia.
    fecha = fecha_ordenable(titular)
    fecha_texto = datetime.fromtimestamp(fecha, COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p") if fecha else "Fecha no disponible"

    cuerpo = f"""
    <main class="articulo ficha-actualidad">
      <div class="articulo-cabecera">
        <a class="volver" href="/">← Volver a CEV NOTICIAS</a>
        <p class="etiqueta">{categoria}</p>
        <p class="fecha">Ficha de seguimiento · Redacción CEV NOTICIAS · Con información de {fuente}</p>
        <h1>{titulo}</h1>
        <p class="bajada">Redacción CEV NOTICIAS registra esta publicación dentro de su seguimiento informativo. El desarrollo periodístico, los datos completos y la cobertura original corresponden al medio citado; consulta allí la noticia íntegra.</p>
        <p class="fecha">Publicado originalmente: {fecha_texto}</p>
      </div>
      <section class="fuentes credito-fuente">
        <strong>Crédito de información y cobertura original</strong>
        <p>La noticia y su desarrollo periodístico fueron publicados originalmente por <strong>{fuente}</strong>.</p>
        <p><a class="boton" href="{url_original}" target="_blank" rel="noopener noreferrer">Consultar la publicación original en {fuente} ↗</a></p>
        <p class="nota-atribucion">Autoría de esta ficha de seguimiento: Redacción CEV NOTICIAS. Crédito de la información, el titular y la cobertura original: {fuente}. Esta ficha no reproduce ni sustituye el artículo del medio citado.</p>
      </section>
    </main>"""

    extra_head = '<meta name="robots" content="noindex,follow">'
    pagina = plantilla(
        titulo,
        cuerpo,
        "Ficha de seguimiento de actualidad de Redacción CEV NOTICIAS, con crédito a la publicación original.",
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
                <p>Los contenidos pueden apoyarse en herramientas automatizadas para localizar fuentes, recuperar documentos, comparar versiones y preparar borradores. Ningún artículo generado automáticamente se publica sin revisión y aprobación editorial humana. La revisión incluye titular, datos principales, contexto, enfoque propio, fuentes y pertinencia de la imagen. Esta revisión no constituye una garantía absoluta de que no existan errores. Las fuentes consultadas se identifican en cada publicación.</p>
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
                <p><strong>CEV NOTICIAS</strong> es un proyecto digital independiente de carácter personal, no constituido como empresa ni sociedad. Es un medio de actualidad con enfoque prioritario en Cali, el Valle del Cauca y Colombia. La cobertura internacional se limita a acontecimientos con repercusión directa y comprobable para el país.</p>
                <p>Nuestro propósito es facilitar el acceso a información reciente mediante noticias organizadas por temas, contexto y referencias a las fuentes consultadas.</p>
                <h2>Qué publicamos</h2><p>Cubrimos actualidad local, regional y nacional, además de deportes, tecnología, economía y tendencias. Nuestra prioridad es Cali y el Valle del Cauca, sin perder de vista los hechos de Colombia. No desarrollamos una cobertura internacional general; solo abordamos acontecimientos extranjeros cuando tienen consecuencias directas y verificables para el país.</p>
                <h2>Cómo trabajamos</h2><p>Utilizamos fuentes identificables, documentos y herramientas digitales para investigar la actualidad, contrastar versiones y preparar contenidos originales. La automatización ayuda a organizar el trabajo, pero no sustituye la verificación ni la decisión editorial. Los artículos generados pasan por revisión humana antes de publicarse. Identificamos las fuentes consultadas y ofrecemos un canal para reportar errores o solicitar aclaraciones.</p>
                <p>Los titulares de medios externos se conservan como material interno de investigación. La portada pública está dedicada a artículos completos de CEV NOTICIAS, con crédito a las fuentes utilizadas en cada cobertura.</p>
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
                <h2>3. Herramientas automatizadas y controles de publicación</h2><p>El seguimiento de fuentes RSS, la investigación documental y la preparación de borradores pueden apoyarse en sistemas automatizados y herramientas de inteligencia artificial. El radar RSS es una herramienta interna de detección: no se publica como un directorio de titulares ni como sustituto de la cobertura periodística. Cada borrador debe incorporar información suficiente, contraste de textos recuperados, enfoque propio, contexto verificable y referencias de origen. Los controles automáticos comprueban extensión, estructura, categoría, duplicados, fuentes HTTPS y atribución; los temas sensibles requieren corroboración independiente. Ningún borrador generado automáticamente se publica por el solo hecho de superar esos controles: se envía a la cola de revisión editorial y requiere aprobación humana antes de incorporarse al sitio. Las fotografías sin licencia y atribución completas se excluyen. Estos controles reducen riesgos, pero no garantizan que nunca existan errores.</p>
                <h2>4. Investigación, autoría y atribución</h2><p>CEV NOTICIAS publica artículos completos elaborados con redacción propia a partir de investigación documental. Una fuente puede haber informado primero sobre el acontecimiento; reconocemos ese origen y enlazamos las publicaciones consultadas, pero no copiamos ni presentamos la cobertura ajena como propia. Las publicaciones externas se conservan como material de investigación interno y no como noticias de portada. Respetamos los derechos de autor y no pretendemos atribuirnos fotografías ni textos ajenos.</p>
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
    Comprueba que cada artículo propio, categoría e imagen del sitio exista
    físicamente dentro del artefacto que se va a desplegar.
    """
    faltantes = []
    esperados = [SITE / "index.html"]
    esperados.extend(SITE / nombre for nombre in ("quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html"))
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
    copiar_ilustraciones_ia()
    datos = cargar_json(CACHE, {})
    noticias = datos.get("noticias", [])
    breves_cache = datos.get("breves", [])
    fecha_edicion_breves = str(datos.get("breves_actualizadas", "")).strip()
    try:
        fecha_edicion = datetime.fromisoformat(fecha_edicion_breves.replace("Z", "+00:00"))
        if fecha_edicion.tzinfo is None:
            fecha_edicion = fecha_edicion.replace(tzinfo=timezone.utc)
        fecha_edicion_breves_texto = fecha_edicion.astimezone(COLOMBIA_TZ).strftime("%d/%m/%Y · %I:%M %p")
    except (ValueError, OverflowError):
        fecha_edicion_breves_texto = ""
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
    breves_publicos = seleccionar_breves_publicos(breves_cache, validas)
    print(
        f"Portada editorial: {len(validas)} artículos completos propios · "
        f"{len(breves_publicos)} mini-noticias rápidas con fuentes acreditadas."
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
    tarjetas_breves = "".join(tarjeta_breve(breve) for breve in breves_publicos)
    # Resumen editorial semanal; la selección se renueva cada cuatro días.
    seccion_breves = f"""
    <section class="bloque-breves" id="ultima-hora" aria-label="Lo más destacado de la semana">
      <div class="breves-encabezado">
        <div>
          <p class="etiqueta">CEV NOTICIAS · RESUMEN DE LA SEMANA</p>
          <h2>Lo más destacado de la semana</h2>
          <p>Un repaso de los hechos más relevantes de Cali, el Valle del Cauca y Colombia, con información consultada y contrastada. Dos ediciones semanales: lunes y viernes a las 6:00 a. m. (hora de Colombia).</p>
          <small class="breves-actualizacion">Edición actualizada: {escapar(fecha_edicion_breves_texto or "En preparación")}</small>
        </div>
        <span class="contador-noticias">{len(breves_publicos)} notas</span>
      </div>
      <div class="breves-grid">
        {tarjetas_breves or '<div class="vacio">Estamos verificando nuevos reportes para preparar las próximas mini-noticias.</div>'}
      </div>
    </section>"""

    # El radar RSS es material de investigación interno. Las páginas públicas
    # contienen exclusivamente artículos completos redactados por CEV NOTICIAS.
    for seccion in SECCIONES:
        crear_pagina_seccion(seccion, validas, [])
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
        f'{seccion_breves}'
        '<section class="bloque-categoria" id="ultimas-noticias">'
        f'<h2 class="titulo-seccion">Noticias propias de CEV NOTICIAS <span class="contador-noticias">{len(validas)} artículos</span></h2>'
        f'<div class="lista-noticias">{lista_portada or "<div class=vacio>No hay noticias propias disponibles por ahora.</div>"}</div>'
        '</section>'
        '<section class="bloque-categoria" id="mas-noticias">'
        f'<h2 class="titulo-seccion">Todas las noticias de CEV NOTICIAS <span class="contador-noticias">{len(validas)} artículos completos</span></h2>'
        '<p class="nota-rss-publica">Los artículos completos y los breves de esta portada son redactados por CEV NOTICIAS. Las fuentes consultadas se acreditan con su nombre; las mini-noticias no redirigen a páginas externas.</p>'
        '</section></main>'
    )
    portada_head = '<link rel="canonical" href="https://cevnoticias.com/"><meta property="og:type" content="website"><meta property="og:title" content="CEV NOTICIAS | Actualidad y periodismo">'
    (SITE / "index.html").write_text(plantilla("Portada", contenido, "Noticias de Cali, Valle del Cauca y Colombia.", extra_head=portada_head, seccion_actual="Portada"), encoding="utf-8")
    recurso_cookies = BASE / "cookies.js"
    if not recurso_cookies.is_file():
        raise RuntimeError("No se encontró cookies.js; no se puede publicar el gestor de consentimiento.")
    shutil.copy2(recurso_cookies, SITE / "cookies.js")
    paginas_institucionales = ["quienes-somos.html", "redaccion.html", "contacto.html", "politica-de-privacidad.html", "politica-editorial.html", "correcciones.html"]
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
    print(
        f"Portada propia creada: {len(validas)} artículos completos. "
        f"Radar RSS interno: {len(titulares_rss)} titulares; no se muestran como fichas públicas."
    )


if __name__ == "__main__":
    construir()