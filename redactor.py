
import os
import re
import json
import time
import hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import requests
import feedparser
import trafilatura
from html import unescape

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from groq import Groq
from imagenes import buscar_imagen

LICENCIAS_VALIDAS = ("cc0", "cc-by", "cc-by-sa", "public domain", "publicdomain", "pdm", "cc-zero")

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache.json")
FEEDS = os.path.join(BASE, "feeds.json")

MODELO = "openai/gpt-oss-20b"
MAX_NOTICIAS = 20
MAX_ARTICULOS_POR_EJECUCION = 2
MAX_SOLICITUDES_POR_EJECUCION = 2
MAX_GRUPOS_REVISADOS_POR_EJECUCION = 12
MINUTOS_ENTRE_SOLICITUDES = 20
MAX_SOLICITUDES_DIARIAS = 40
MAX_TITULARES_POR_CATEGORIA = 10
MAX_EDAD_TITULARES_HORAS = 72
MAX_ARTICULOS_ANTERIORES = 150
MAX_EDAD_HORAS = 168
SITE = Path(BASE) / "site"

CATEGORIAS = [
    "Cali",
    "Valle del Cauca",
    "Colombia",
    "Internacional",
    "Deportes",
    "Tecnología",
    "Economía",
    "Tendencias",
    "Humor y opinión"
]

IGNORAR = {
    "para", "desde", "sobre", "entre", "tras", "cuando",
    "donde", "porque", "segun", "como", "esta", "este",
    "estos", "estas", "tambien", "contra", "despues",
    "antes", "hacia", "hasta", "ante", "seran", "sera",
    "fue", "son", "los", "las", "una", "uno", "del",
    "por", "con", "sin", "que", "sus", "como", "más",
    "mas", "hoy", "ayer", "nuevo", "nueva", "tras"
}

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CEVNoticias/1.0; "
        "+https://7zkm57snty-dev.github.io/noti/)"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, text/html"
}


def leer_json(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return defecto


def guardar_json(ruta, datos):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def fecha_entrada(entrada):
    for campo in ("published_parsed", "updated_parsed"):
        try:
            valor = getattr(entrada, campo, None)
            if valor:
                return datetime(*valor[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    return datetime.now(timezone.utc)


def url_imagen_entrada(entrada):
    candidatos = []

    for campo in ("media_content", "media_thumbnail"):
        elementos = entrada.get(campo, []) or []
        if isinstance(elementos, dict):
            elementos = [elementos]
        for elemento in elementos:
            if isinstance(elemento, dict):
                candidatos.append(elemento.get("url", ""))

    for elemento in entrada.get("enclosures", []) or []:
        if isinstance(elemento, dict):
            tipo = elemento.get("type", "")
            if tipo.startswith("image/") or not tipo:
                candidatos.append(elemento.get("href") or elemento.get("url", ""))

    for campo in ("summary", "description"):
        html_resumen = entrada.get(campo, "") or ""
        candidatos.extend(re.findall(
            r"<img[^>]+src=[\"']([^\"']+)[\"']",
            html_resumen,
            flags=re.IGNORECASE
        ))

    for imagen in candidatos:
        imagen = unescape(str(imagen)).strip()
        if imagen.startswith(("https://", "http://")):
            return imagen

    return ""


def obtener_imagen_pagina(url):
    try:
        respuesta = requests.get(url, headers=CABECERAS, timeout=15)
        respuesta.raise_for_status()
        html_pagina = respuesta.text[:500000]

        patrones = [
            r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:image[\"']",
            r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']twitter:image[\"']"
        ]

        for patron in patrones:
            coincidencia = re.search(patron, html_pagina, flags=re.IGNORECASE)
            if coincidencia:
                imagen = unescape(coincidencia.group(1)).strip()
                if imagen.startswith(("https://", "http://")):
                    return imagen

    except Exception as error:
        print("No se pudo recuperar la imagen:", error)

    return ""


def obtener_fuentes():
    configuracion = leer_json(FEEDS, [])

    if isinstance(configuracion, dict):
        configuracion = configuracion.get("feeds", [])

    resultados = []
    limite = datetime.now(timezone.utc) - timedelta(
        hours=MAX_EDAD_HORAS
    )

    for feed in configuracion:
        url_feed = feed.get("url")
        nombre = feed.get("nombre", "Fuente")

        if not url_feed:
            continue

        try:
            respuesta = requests.get(
                url_feed,
                headers=CABECERAS,
                timeout=20
            )
            respuesta.raise_for_status()

            datos = feedparser.parse(respuesta.content)

            if not datos.entries:
                print("RSS sin noticias:", nombre)
                continue

            print(
                f"Fuente disponible: {nombre} "
                f"({len(datos.entries)} entradas)"
            )

            for entrada in datos.entries[:40]:
                fecha = fecha_entrada(entrada)

                if fecha < limite:
                    continue

                titulo = entrada.get("title", "").strip()
                enlace = entrada.get("link", "").strip()

                if not titulo:
                    continue

                if not enlace.startswith(("https://", "http://")):
                    continue

                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fuente": nombre,
                    "fecha": fecha.isoformat(),
                    "imagen": url_imagen_entrada(entrada)
                })

        except Exception as error:
            print(f"No se pudo leer {nombre}: {error}")

    resultados.sort(
        key=lambda noticia: noticia["fecha"],
        reverse=True
    )

    print("Total de noticias encontradas en RSS:", len(resultados))
    return resultados


def extraer_articulo(url):
    try:
        respuesta = requests.get(
            url,
            headers=CABECERAS,
            timeout=25
        )
        respuesta.raise_for_status()

        texto = trafilatura.extract(
            respuesta.text,
            include_comments=False,
            include_tables=False,
            favor_precision=True
        )

        if texto:
            return texto.strip()

        return ""

    except Exception as error:
        print("No se pudo recuperar el artículo:", error)
        return ""


def palabras_importantes(texto):
    palabras = re.findall(
        r"[a-záéíóúñü]{4,}",
        texto.lower()
    )

    return {
        palabra for palabra in palabras
        if palabra not in IGNORAR
    }


def son_misma_noticia(titulo_a, titulo_b):
    palabras_a = palabras_importantes(titulo_a)
    palabras_b = palabras_importantes(titulo_b)

    if not palabras_a or not palabras_b:
        return False

    comunes = palabras_a.intersection(palabras_b)
    union = palabras_a.union(palabras_b)

    similitud = len(comunes) / max(1, len(union))

    # Se requiere coincidencia temática suficiente,
    # sin exigir titulares prácticamente idénticos.
    return len(comunes) >= 2 and similitud >= 0.20


def agrupar_noticias(entradas):
    grupos = []

    for entrada in entradas:
        grupo_encontrado = None

        for grupo in grupos:
            if son_misma_noticia(
                entrada["titulo"],
                grupo["titulo"]
            ):
                grupo_encontrado = grupo
                break

        if grupo_encontrado is None:
            grupos.append({
                "titulo": entrada["titulo"],
                "fuentes": [entrada]
            })
        else:
            dominios = {
                urlparse(f["url"]).netloc.lower()
                for f in grupo_encontrado["fuentes"]
            }

            dominio_actual = urlparse(
                entrada["url"]
            ).netloc.lower()

            if dominio_actual not in dominios:
                grupo_encontrado["fuentes"].append(entrada)

    return grupos


def prioridad_regional(grupo):
    """
    Da prioridad a los hechos de Cali y del Valle del Cauca para que
    no consuman primero el cupo diario las noticias internacionales.
    """
    titulo = str(grupo.get("titulo", "")).lower()
    fuentes = grupo.get("fuentes", [])
    nombres = " ".join(str(f.get("fuente", "")).lower() for f in fuentes)
    texto = f"{titulo} {nombres}"

    puntos = 0
    if any(nombre in nombres for nombre in ("el tiempo cali", "90 minutos", "diario occidente")):
        puntos += 12

    localidades = (
        "cali", "valle del cauca", "jamundi", "jamundí", "palmira",
        "yumbo", "tulua", "tuluá", "buenaventura", "buga", "cartago",
        "candelaria", "dagua", "roldanillo", "guacari", "guacarí",
        "ginebra", "pradera", "el cerrito", "zarzal", "sevilla",
        "caicedonia", "restrepo", "la victoria", "versalles",
        "trujillo", "riofrio", "riofrío", "san pedro", "la union",
        "la unión", "andalucia", "andalucía", "el dovio", "el dovío",
        "ulloa", "obando", "argelia"
    )
    if any(lugar in texto for lugar in localidades):
        puntos += 8

    return puntos


def fecha_mas_reciente_grupo(grupo):
    fechas = []
    for fuente in grupo.get("fuentes", []):
        try:
            fechas.append(datetime.fromisoformat(str(fuente.get("fecha", "")).replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError, OverflowError):
            continue
    return max(fechas, default=0)


def leer_contenidos(grupo):
    fuentes_validas = []

    # Dos medios independientes bastan para contrastar sin inflar el contexto.
    for fuente in grupo["fuentes"][:2]:
        texto = extraer_articulo(fuente["url"])

        if len(texto) < 500:
            print(
                "Texto insuficiente:",
                fuente["fuente"],
                fuente["titulo"]
            )
            continue

        fuentes_validas.append({
            "nombre": fuente["fuente"],
            "titulo": fuente["titulo"],
            "url": fuente["url"],
            "texto": texto[:4500]
        })

    return fuentes_validas


def generar_articulo(cliente, titulo_referencia, fuentes):
    material = []

    for fuente in fuentes:
        material.append(
            f"""
MEDIO: {fuente['nombre']}
TÍTULO: {fuente['titulo']}
INFORMACIÓN:
{fuente['texto']}
"""
        )

    instrucciones = f"""
Eres periodista de CEV NOTICIAS, un periódico digital
independiente dirigido al público colombiano.

Debes elaborar un artículo periodístico ORIGINAL.

TÍTULO DE REFERENCIA:
{titulo_referencia}

INFORMACIÓN DE LOS MEDIOS:
{''.join(material)}

REGLAS PERIODÍSTICAS:

1. Utiliza únicamente hechos respaldados por las fuentes.
2. No copies los artículos originales.
3. No inventes nombres, fechas, cifras, declaraciones ni acontecimientos.
4. Contrasta los datos entre los medios.
5. Si hay contradicciones importantes, descarta la noticia.
6. No inventes citas textuales.
7. No presentes rumores como hechos confirmados.
8. Explica qué ocurrió, dónde, cuándo y por qué es relevante,
   siempre que las fuentes permitan responderlo.
9. Redacta en español colombiano, con estilo periodístico
   claro, profesional y natural.
10. No incluyas enlaces externos dentro del artículo.
11. No incluyas publicidad ni contenido promocional.
12. No rellenes el texto con opiniones o información inventada.
13. Si no existe suficiente información para un artículo
    desarrollado, responde con "descartar": true.
14. Para accidentes, homicidios, robos, hurtos, capturas,
    víctimas, denuncias y controversias políticas, exige
    corroboración de al menos dos fuentes independientes.
    Si solo hay una fuente, descarta el artículo. En noticias
    generales de bajo riesgo puede bastar una fuente fiable,
    siempre atribuyendo la información.
15. Distingue los comunicados oficiales de los hechos
    confirmados de manera independiente. Atribuye siempre
    la información a la entidad que la comunica.
16. La categoría "Tendencias" solo se usa cuando el tema
    muestra atención creciente o aparece en varias fuentes.
17. "Humor y opinión" se reserva para sátira y humor
    claramente identificados; nunca inventes hechos ni
    presentes una broma como noticia real.
18. Mantén el humor ocasional y minoritario frente a
    la cobertura informativa.
19. No incluyas contenido promocional ni datos que no estén respaldados.

La extensión deseada es de 350 a 550 palabras,
pero nunca debes inventar información para alcanzar esa extensión.

Elige UNA categoría correcta de esta lista:
{", ".join(CATEGORIAS)}

No clasifiques una noticia local como internacional.
No clasifiques una noticia deportiva en Colombia si
su tema principal es el deporte.

CRITERIO TERRITORIAL OBLIGATORIO:
- "Cali": el hecho ocurre principalmente dentro de Santiago de Cali.
- "Valle del Cauca": el hecho ocurre en otro municipio del departamento.
- "Colombia": el hecho ocurre en otra región del país o es de alcance nacional.
- "Internacional": el hecho ocurre fuera de Colombia.
No uses "Colombia" para ocultar una noticia que corresponde a Cali
o a otro municipio del Valle del Cauca.

ESTADO DE LA INFORMACIÓN:
- Usa "confirmada" cuando los hechos centrales estén respaldados
  por las fuentes disponibles y no haya contradicciones relevantes.
- Usa "en_desarrollo" cuando el acontecimiento siga ocurriendo,
  las autoridades aún estén verificando datos o el balance pueda cambiar.
- Usa "informacion_preliminar" cuando los datos centrales procedan
  de reportes iniciales, versiones no confirmadas o información parcial.
- No marques una noticia como preliminar solo por tener una fuente:
  evalúa si esa fuente respalda claramente los hechos publicados.
- Nunca inventes confirmaciones, cifras, causas ni responsables.
- Si una afirmación relevante no está confirmada, atribúyela a su fuente
  y marca el estado correspondiente.

Devuelve exclusivamente JSON válido con esta estructura:

{{
  "descartar": false,
  "titulo": "Título original",
  "titular_instagram": "Titular breve, llamativo y fiel a los hechos",
  "resumen": "Resumen de la noticia",
  "categoria": "Categoría",
  "estado_informacion": "confirmada | en_desarrollo | informacion_preliminar",
  "contenido": "Artículo completo con párrafos separados"
}}
"""

    respuesta = cliente.chat.completions.create(
        model=MODELO,
        messages=[{"role": "user", "content": instrucciones}],
        temperature=0.2,
        reasoning_format="hidden"
    )

    contenido_respuesta = respuesta.choices[0].message.content
    if not contenido_respuesta:
        return None

    try:
        articulo = json.loads(contenido_respuesta)
    except json.JSONDecodeError:
        print("Groq devolvió una respuesta no válida.")
        return None

    if articulo.get("descartar") is True:
        print("Noticia descartada por falta de información.")
        return None

    if articulo.get("categoria") not in CATEGORIAS:
        return None

    titulo = str(articulo.get("titulo", "")).strip()
    titular_instagram = str(articulo.get("titular_instagram", "")).strip()
    resumen = str(articulo.get("resumen", "")).strip()
    contenido = str(articulo.get("contenido", "")).strip()

    if not titulo or not resumen:
        return None

    if len(contenido.split()) < 250:
        print("Artículo demasiado corto.")
        return None

    estado_informacion = str(articulo.get("estado_informacion", "actualidad")).strip().lower()
    if estado_informacion not in ("actualidad", "confirmada", "en_desarrollo", "informacion_preliminar"):
        estado_informacion = "actualidad"

    return {
        "titulo": titulo,
        "titular_instagram": titular_instagram or titulo,
        "resumen": resumen,
        "categoria": articulo["categoria"],
        "contenido": contenido,
        "estado_informacion": estado_informacion,
        "descripcion_instagram": str(articulo.get("descripcion_instagram", "")).strip()
    }



def _fuente_social(negrita, tamano):
    rutas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrita else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if negrita else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]
    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def crear_portada_instagram(identificador, titular, categoria, foto_url):
    """
    Crea una portada editorial 4:5. Usa una fotografía con licencia
    cuando existe; de lo contrario genera una portada gráfica CEV.
    """
    carpeta = SITE / "social"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{identificador}.jpg"

    from io import BytesIO
    foto_real = False
    if foto_url:
        try:
            respuesta = requests.get(foto_url, headers=CABECERAS, timeout=25)
            respuesta.raise_for_status()
            foto = Image.open(BytesIO(respuesta.content)).convert("RGB")
            ancho, alto = foto.size
            escala = max(1080 / ancho, 1350 / alto)
            foto = foto.resize((int(ancho * escala), int(alto * escala)), Image.Resampling.LANCZOS)
            izquierda = (foto.width - 1080) // 2
            arriba = (foto.height - 1350) // 2
            imagen = foto.crop((izquierda, arriba, izquierda + 1080, arriba + 1350)).convert("RGBA")
            foto_real = True
        except Exception as error:
            print("No se pudo usar la fotografía; se creará portada gráfica CEV:", error)

    if not foto_real:
        imagen = Image.new("RGBA", (1080, 1350), (24, 24, 24, 255))
        fondo = ImageDraw.Draw(imagen)
        for y_grad in range(1350):
            tono = int(32 + 28 * (y_grad / 1350))
            fondo.line((0, y_grad, 1080, y_grad), fill=(tono, 17, 21, 255))
        fondo.ellipse((650, 230, 1260, 840), outline=(190, 40, 50, 120), width=9)
        fondo.ellipse((735, 315, 1175, 755), outline=(190, 40, 50, 80), width=5)
        fondo.text((76, 235), "EDICIÓN DIGITAL", font=_fuente_social(True, 26), fill="#ff6b72")
        fondo.text((76, 310), "INFORMACIÓN", font=_fuente_social(True, 54), fill="#ffffff")
        fondo.text((76, 380), "CON CONTEXTO", font=_fuente_social(True, 54), fill="#ffffff")

    # Oscurecimiento progresivo en la parte inferior para asegurar legibilidad.
    degradado = Image.new("RGBA", (1080, 1350), (0, 0, 0, 0))
    pixeles = degradado.load()
    inicio = 470
    for y in range(inicio, 1350):
        proporcion = (y - inicio) / (1350 - inicio)
        alpha = int(35 + 205 * proporcion)
        for x in range(1080):
            pixeles[x, y] = (8, 12, 18, alpha)
    imagen = Image.alpha_composite(imagen, degradado)
    d = ImageDraw.Draw(imagen)

    rojo = "#c62832"
    blanco = "#ffffff"
    margen = 76
    d.rectangle((0, 0, 1080, 16), fill=rojo)
    d.rounded_rectangle((margen, 64, 350, 125), radius=10, fill=rojo)
    d.text((margen + 20, 77), "CEV NOTICIAS", font=_fuente_social(True, 30), fill=blanco)
    d.text((margen, 845), str(categoria).upper()[:32], font=_fuente_social(True, 28), fill="#ff6b72")

    titular = re.sub(r"\s+", " ", str(titular)).strip()
    fuente = _fuente_social(True, 76)
    max_ancho = 928
    lineas = []
    actual = ""
    for palabra in titular.split():
        prueba = (actual + " " + palabra).strip()
        if d.textbbox((0, 0), prueba, font=fuente)[2] > max_ancho and actual:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        lineas.append(actual)

    while len(lineas) > 4 and fuente.size > 48:
        fuente = _fuente_social(True, fuente.size - 4)
        lineas = []
        actual = ""
        for palabra in titular.split():
            prueba = (actual + " " + palabra).strip()
            if d.textbbox((0, 0), prueba, font=fuente)[2] > max_ancho and actual:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        if actual:
            lineas.append(actual)

    y = 900
    alto_linea = fuente.size + 10
    for linea in lineas[:4]:
        d.text((margen + 2, y + 3), linea, font=fuente, fill=(0, 0, 0, 180), stroke_width=1)
        d.text((margen, y), linea, font=fuente, fill=blanco)
        y += alto_linea

    d.line((margen, 1285, 1004, 1285), fill=rojo, width=5)
    d.text((margen, 1300), "PERIODISMO · CONTEXTO · ACTUALIDAD",
           font=_fuente_social(True, 19), fill="#e7e7e7")

    imagen.convert("RGB").save(ruta, "JPEG", quality=92, optimize=True)
    return f"https://cevnoticias.com/social/{identificador}.jpg"


def crear_caption_instagram(articulo, imagen_info):
    caption = str(articulo.get("descripcion_instagram", "")).strip()
    if not caption:
        caption = f"{articulo['titulo']}\\n\\n{articulo['resumen']}"
    # Mantener las descripciones sobrias: como máximo un emoji.
    emojis = ["📰", "📍", "🚨", "🔥", "⚠️", "📢", "👇", "➡️", "✅", "⭐"]
    for emoji in emojis:
        caption = caption.replace(emoji, "")
    categoria = articulo.get("categoria", "")
    lugar = "Cali" if categoria == "Cali" else ("Valle del Cauca" if categoria == "Valle del Cauca" else "")
    if lugar and lugar.lower() not in caption.lower():
        caption += f"\\n\\n📍 {lugar}"
    caption += "\\n\\nLee la noticia completa en cevnoticias.com."
    hashtags = ["#CEVNoticias", "#Actualidad"]
    if categoria == "Cali":
        hashtags += ["#Cali", "#ValleDelCauca"]
    elif categoria == "Valle del Cauca":
        hashtags += ["#ValleDelCauca", "#Colombia"]
    elif categoria == "Deportes":
        hashtags += ["#Deportes", "#Colombia"]
    elif categoria == "Tecnología":
        hashtags += ["#Tecnología", "#Colombia"]
    elif categoria == "Internacional":
        hashtags += ["#Internacional"]
    else:
        hashtags += ["#Colombia"]
    if imagen_info:
        caption += f"\\n\\nImagen: {imagen_info.get('autor', 'Autor no identificado')} · {imagen_info.get('fuente', 'Archivo')} · {imagen_info.get('licencia', '')}"
    return caption[:1700] + "\\n\\n" + " ".join(hashtags[:5])


def identificador_articulo(titulo):
    return hashlib.sha256(
        titulo.lower().encode("utf-8")
    ).hexdigest()[:16]


def asegurar_datos_instagram(noticias):
    """
    Garantiza una fotografía real con licencia reutilizable para web e Instagram.
    No sustituye fotografías por carteles, portadas de texto ni gráficos propios.
    """
    imagenes_encontradas = 0
    imagenes_pendientes = 0
    descripciones_creadas = 0

    for noticia in noticias:
        if not isinstance(noticia, dict):
            continue

        identificador = str(noticia.get("id", "")).strip()
        titulo = str(noticia.get("titulo", "")).strip()
        if not identificador or not titulo:
            continue

        credito = noticia.get("imagen_credito") or {}
        imagen_actual = str(noticia.get("imagen", "")).strip()
        licencia_actual = str(credito.get("licencia", "")).lower()
        licencia_apta = any(x in licencia_actual for x in LICENCIAS_VALIDAS) and not any(x in licencia_actual for x in ("nc", "nd")) and bool(credito.get("pagina") and credito.get("licencia_url"))

        if (not imagen_actual.startswith("https://") or not licencia_apta) and not noticia.get("imagen_busqueda_intentada"):
            print("Buscando fotografía real con licencia para:", titulo)
            imagen_info = buscar_imagen(
                titulo,
                noticia.get("resumen", ""),
                noticia.get("categoria", "")
            )
            noticia["imagen_busqueda_intentada"] = True
            if imagen_info:
                noticia["imagen"] = imagen_info["url"]
                noticia["imagen_credito"] = imagen_info
                noticia["imagen_instagram"] = imagen_info["url"]
                noticia["imagen_instagram_tipo"] = "externa_con_licencia"
                imagenes_encontradas += 1
            else:
                noticia["imagen"] = ""
                noticia["imagen_instagram"] = ""
                noticia["imagen_instagram_tipo"] = "portada_grafica_cev"
                noticia["imagen_credito"] = {}
                imagenes_pendientes += 1
        else:
            noticia["imagen_instagram"] = imagen_actual
            noticia["imagen_instagram_tipo"] = "externa_con_licencia"

        if not str(noticia.get("descripcion_instagram", "")).strip():
            noticia["descripcion_instagram"] = crear_caption_instagram(
                noticia,
                noticia.get("imagen_credito") or {}
            )
            descripciones_creadas += 1

    print(
        "Control de imágenes reales: "
        f"{imagenes_encontradas} fotografías encontradas, "
        f"{imagenes_pendientes} noticias sin fotografía apta, "
        f"{descripciones_creadas} descripciones completadas."
    )


def categoria_titular_rss(entrada):
    titulo = str(entrada.get("titulo", "")).lower()
    fuente = str(entrada.get("fuente", "")).lower()

    municipios_valle = (
        "jamundi", "jamundí", "palmira", "yumbo", "tulua", "tuluá",
        "buenaventura", "buga", "cartago", "candelaria", "dagua",
        "roldanillo", "guacari", "guacarí", "ginebra", "pradera",
        "el cerrito", "zarzal", "sevilla", "caicedonia", "restrepo",
        "la victoria", "versalles", "trujillo", "riofrio", "riofrío",
        "san pedro", "la union", "la unión", "andalucia", "andalucía",
        "el dovio", "el dovío", "ulloa", "obando", "argelia"
    )

    hechos_no_deportivos = (
        "accidente", "atentado", "muertos", "muerto", "muerte",
        "homicidio", "asesin", "captur", "víctima", "victima",
        "herido", "explosiv", "robo", "asalto", "secuestro",
        "crimen", "disparos", "desaparec", "incendio", "volqueta"
    )
    menciona_hecho_no_deportivo = any(p in titulo for p in hechos_no_deportivos)
    es_titular_deportivo = (
        "la fm deportes" in fuente or any(p in titulo for p in (
            "fútbol", "futbol", "liga", "selección", "seleccion", "partido",
            "mundial", "copa", "tenis", "ciclismo", "baloncesto", "nba",
            "deporte", "deportivo", "fórmula 1", "formula 1", "torneo"
        ))
    )
    if es_titular_deportivo and not menciona_hecho_no_deportivo:
        return "Deportes"

    if any(municipio in titulo for municipio in municipios_valle) or "valle del cauca" in titulo:
        return "Valle del Cauca"
    if re.search(r"\bcali\b", titulo) or fuente == "el tiempo cali":
        return "Cali"
    if "90 minutos" in fuente or "diario occidente" in fuente:
        return "Valle del Cauca"

    if "la fm economía" in fuente or "portafolio" in fuente or any(p in titulo for p in (
        "economía", "economia", "inflación", "inflacion", "dólar", "dolar",
        "empresas", "mercado", "finanzas", "banco", "inversión", "inversion"
    )):
        return "Economía"
    if "la fm internacional" in fuente:
        return "Internacional"
    if "xataka" in fuente or any(p in titulo for p in (
        "inteligencia artificial", "tecnología", "tecnologia", "software",
        "aplicación", "aplicacion", "ciberseguridad", "smartphone",
        "celular", "computador", "videojuego"
    )):
        return "Tecnología"

    paises_extranjeros = (
        "ucrania", "rusia", "estados unidos", "ee.uu", "eeuu", "méxico", "mexico",
        "argentina", "brasil", "perú", "peru", "ecuador", "bolivia", "chile",
        "israel", "gaza", "palestina", "irán", "iran", "china", "japón", "japon",
        "reino unido", "francia", "alemania", "italia", "españa", "canadá", "canada",
        "haití", "haiti", "cuba", "nicaragua", "honduras", "guatemala", "siria",
        "líbano", "libano", "pakistán", "pakistan", "india", "sudán", "sudan",
        "etiopía", "etiopia", "nigeria", "kenia", "sudáfrica", "sudafrica",
        "taiwán", "taiwan", "corea", "afganistán", "afganistan"
    )
    if any(pais in titulo for pais in paises_extranjeros):
        return "Internacional"
    if any(p in fuente for p in ("bbc mundo", "dw español")):
        return "Internacional"

    return "Colombia"


def fecha_a_timestamp(valor):
    try:
        fecha = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def construir_titulares_rss(entradas, publicadas, anteriores):
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=MAX_EDAD_TITULARES_HORAS)
    grupos_rss = agrupar_noticias(entradas)
    candidatos = []

    for grupo in grupos_rss:
        fuentes = grupo.get("fuentes", [])
        if not fuentes:
            continue

        fuente = max(fuentes, key=lambda f: fecha_a_timestamp(f.get("fecha")))
        fecha_ts = fecha_a_timestamp(fuente.get("fecha"))
        if not fecha_ts or fecha_ts < limite.timestamp() or fecha_ts > (ahora + timedelta(hours=2)).timestamp():
            continue

        titulo = str(fuente.get("titulo") or grupo.get("titulo") or "").strip()
        if not titulo:
            continue

        if any(son_misma_noticia(titulo, n.get("titulo", "")) for n in publicadas if n.get("titulo")):
            continue

        categoria = categoria_titular_rss({**fuente, "titulo": titulo})
        url = str(fuente.get("url") or "")
        if not url.startswith(("https://", "http://")):
            continue

        candidatos.append({
            "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
            "titulo": titulo,
            "categoria": categoria,
            "fuente": str(fuente.get("fuente") or "Medio de origen"),
            "url": url,
            "fecha": str(fuente.get("fecha") or ""),
            "imagen": str(fuente.get("imagen") or "")
        })

    anteriores_validos = []
    for anterior in (anteriores if isinstance(anteriores, list) else []):
        if str(anterior.get("fuente", "")) == "BBC Sport":
            continue
        anterior = dict(anterior)
        anterior["categoria"] = categoria_titular_rss({
            "titulo": anterior.get("titulo", ""),
            "fuente": anterior.get("fuente", "")
        })
        anteriores_validos.append(anterior)

    candidatos.extend(anteriores_validos)
    candidatos.sort(key=lambda n: fecha_a_timestamp(n.get("fecha")), reverse=True)

    resultado = []
    urls_vistas = set()
    titulos_vistos = []
    conteo = {}

    for titular in candidatos:
        url = str(titular.get("url", "")).strip()
        titulo = str(titular.get("titulo", "")).strip()
        categoria = titular.get("categoria")

        if not url.startswith(("https://", "http://")) or not titulo or categoria not in CATEGORIAS:
            continue
        if fecha_a_timestamp(titular.get("fecha")) < limite.timestamp() or url in urls_vistas:
            continue
        if any(son_misma_noticia(titulo, anterior) for anterior in titulos_vistos):
            continue
        if any(son_misma_noticia(titulo, n.get("titulo", "")) for n in publicadas if n.get("titulo")):
            continue
        if conteo.get(categoria, 0) >= MAX_TITULARES_POR_CATEGORIA:
            continue

        resultado.append({
            "id": str(titular.get("id") or hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]),
            "titulo": titulo,
            "categoria": categoria,
            "fuente": str(titular.get("fuente") or "Medio de origen"),
            "url": url,
            "fecha": str(titular.get("fecha") or ""),
            "imagen": str(titular.get("imagen") or "")
        })
        urls_vistas.add(url)
        titulos_vistos.append(titulo)
        conteo[categoria] = conteo.get(categoria, 0) + 1

    print("Titulares RSS visibles:", len(resultado), "| por sección:", conteo)
    return resultado


def ejecutar():
    api_key = os.environ.get("GROQ_API_KEY")
    cliente = Groq(api_key=api_key) if api_key else None
    if not api_key:
        print("GROQ_API_KEY no configurada: se actualizarán titulares RSS sin generar artículos propios.")

    cache = leer_json(CACHE, {"noticias": []})

    if not isinstance(cache, dict):
        cache = {"noticias": []}

    publicadas = cache.get("noticias", [])

    if not isinstance(publicadas, list):
        publicadas = []

    titulos_publicados = [
        noticia.get("titulo", "")
        for noticia in publicadas
    ]

    entradas = obtener_fuentes()
    titulares_rss = construir_titulares_rss(
        entradas,
        publicadas,
        cache.get("titulares_rss", [])
    )

    # Descarta titulares ya publicados.
    entradas_nuevas = [
        entrada for entrada in entradas
        if not any(
            son_misma_noticia(
                entrada["titulo"],
                titulo
            )
            for titulo in titulos_publicados
            if titulo
        )
    ]

    print("Noticias nuevas para revisar:", len(entradas_nuevas))

    grupos = agrupar_noticias(entradas_nuevas)
    grupos.sort(
        key=lambda grupo: (prioridad_regional(grupo), fecha_mas_reciente_grupo(grupo)),
        reverse=True
    )

    print("Grupos temáticos encontrados:", len(grupos))
    print("Prioridad aplicada: Cali y Valle del Cauca antes de cobertura general.")

    nuevas = []
    fecha_control = datetime.now(
        timezone(timedelta(hours=-5))
    ).strftime("%Y-%m-%d")

    if cache.get("fecha_solicitudes_groq") != fecha_control:
        solicitudes_groq = 0
    else:
        solicitudes_groq = int(cache.get("solicitudes_groq", 0))

    print(
        f"Solicitudes Groq usadas hoy: {solicitudes_groq}/"
        f"{MAX_SOLICITUDES_DIARIAS}"
    )

    ultima_solicitud_groq = cache.get("ultima_solicitud_groq", "")
    timestamp_ultima = fecha_a_timestamp(ultima_solicitud_groq)
    ahora_ts = datetime.now(timezone.utc).timestamp()
    puede_generar = bool(cliente) and solicitudes_groq < MAX_SOLICITUDES_DIARIAS

    if puede_generar and timestamp_ultima and (ahora_ts - timestamp_ultima) < MINUTOS_ENTRE_SOLICITUDES * 60:
        puede_generar = False
        print("Pausa de consumo activa: los titulares RSS sí se actualizan en este ciclo.")
    if solicitudes_groq >= MAX_SOLICITUDES_DIARIAS:
        print("Cupo diario de artículos originales agotado. Se mantienen actualizados los titulares RSS.")

    grupos_revisados = 0
    solicitudes_esta_ejecucion = 0

    if puede_generar:
        for grupo in grupos:
            if len(nuevas) >= MAX_ARTICULOS_POR_EJECUCION:
                break
            if solicitudes_esta_ejecucion >= MAX_SOLICITUDES_POR_EJECUCION:
                break
            if grupos_revisados >= MAX_GRUPOS_REVISADOS_POR_EJECUCION:
                print("Límite de grupos revisados en esta ejecución alcanzado.")
                break

            grupos_revisados += 1
            fuentes = leer_contenidos(grupo)

            dominios = {
                urlparse(f["url"]).netloc.lower()
                for f in fuentes
            }

            if len(fuentes) < 1:
                print("Noticia sin contenido recuperable:", grupo["titulo"])
                continue

            try:
                solicitudes_groq += 1
                solicitudes_esta_ejecucion += 1
                ultima_solicitud_groq = datetime.now(timezone.utc).isoformat()

                articulo = generar_articulo(cliente, grupo["titulo"], fuentes)

                if not articulo:
                    print("Tema descartado o respuesta insuficiente; se revisará el siguiente grupo.")
                    continue

                identificador = identificador_articulo(articulo["titulo"])

                if any(n.get("id") == identificador for n in publicadas + nuevas):
                    print("Se omite un artículo con identificador ya publicado:", articulo["titulo"])
                    continue

                if any(
                    son_misma_noticia(articulo["titulo"], n.get("titulo", ""))
                    for n in publicadas + nuevas if n.get("titulo")
                ):
                    print("Se omite un artículo duplicado por similitud:", articulo["titulo"])
                    continue

                imagen_info = buscar_imagen(
                    articulo["titulo"],
                    articulo["resumen"],
                    articulo["categoria"]
                )

                if not imagen_info or not imagen_info.get("url"):
                    print("No hay fotografía libre adecuada; se usará una portada gráfica original de CEV:", articulo["titulo"])
                    imagen_info = None

                caption_instagram = crear_caption_instagram(articulo, imagen_info or {})
                titular_social = articulo.get("titular_instagram") or articulo["titulo"]
                try:
                    portada_social = crear_portada_instagram(
                        identificador,
                        titular_social,
                        articulo["categoria"],
                        imagen_info["url"] if imagen_info else ""
                    )
                except Exception as error:
                    print("No se pudo diseñar la portada de esta noticia:", error)
                    continue

                nuevas.append({
                    "id": identificador,
                    "titulo": articulo["titulo"],
                    "titular_instagram": articulo.get("titular_instagram") or articulo["titulo"],
                    "resumen": articulo["resumen"],
                    "categoria": articulo["categoria"],
                    "contenido": articulo["contenido"],
                    "estado_informacion": articulo.get("estado_informacion", "confirmada"),
                    "imagen": imagen_info["url"] if imagen_info else "",
                    "imagen_credito": imagen_info or {},
                    "imagen_busqueda_intentada": True,
                    "imagen_instagram": portada_social,
                    "imagen_instagram_tipo": "portada_editorial_con_fotografia" if imagen_info else "portada_grafica_cev",
                    "descripcion_instagram": caption_instagram,
                    "verificacion": (
                        "Varias fuentes independientes"
                        if len(dominios) >= 2
                        else "Una sola fuente"
                    ),
                    "fecha": datetime.now(
                        timezone(timedelta(hours=-5))
                    ).strftime("%d/%m/%Y · %I:%M %p"),
                    "fuentes": [
                        {"nombre": fuente["nombre"], "titulo": fuente["titulo"], "url": fuente["url"]}
                        for fuente in fuentes
                    ]
                })

                print("Artículo creado:", articulo["titulo"])
                if solicitudes_esta_ejecucion < MAX_SOLICITUDES_POR_EJECUCION:
                    print("Pausa de 65 segundos antes de la siguiente generación para respetar el límite de tokens por minuto.")
                    time.sleep(65)

            except Exception as error:
                print("Error al generar artículo:", str(error))
                print("Se detiene el intento para respetar el cupo del modelo.")
                break
    else:
        print("En esta ejecución no corresponde consumir una solicitud de Groq.")

    resultado = nuevas + publicadas
    resultado = resultado[:MAX_ARTICULOS_ANTERIORES]

    # Completa también las noticias que ya estaban en la web para que
    # puedan entrar a la cola de Instagram sin esperar a nuevos artículos.
    asegurar_datos_instagram(resultado)

    guardar_json(CACHE, {
        "noticias": resultado,
        "titulares_rss": titulares_rss,
        "ultima_solicitud_groq": ultima_solicitud_groq,
        "fecha_solicitudes_groq": fecha_control,
        "solicitudes_groq": solicitudes_groq,
        "ultima_actualizacion": datetime.now(
            timezone.utc
        ).isoformat()
    })

    print("--------------------------------")
    print("Artículos nuevos:", len(nuevas))
    print("Total de artículos:", len(resultado))
    print("--------------------------------")


if __name__ == "__main__":
    ejecutar()
