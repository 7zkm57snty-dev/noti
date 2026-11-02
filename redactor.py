
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

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache.json")
FEEDS = os.path.join(BASE, "feeds.json")

MODELO = "openai/gpt-oss-20b"
MAX_NOTICIAS = 20
MAX_ARTICULOS_POR_EJECUCION = 2
MAX_SOLICITUDES_DIARIAS = 18
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


def leer_contenidos(grupo):
    fuentes_validas = []

    for fuente in grupo["fuentes"]:
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
            "texto": texto[:7500]
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
19. Crea una descripción independiente para Instagram, breve,
    atractiva y fiel a los hechos. No copies el resumen literalmente.
    Usa como máximo un emoji, ubicación solo si está confirmada
    y entre 3 y 5 hashtags pertinentes. No inventes datos.

La extensión deseada es de 350 a 550 palabras,
pero nunca debes inventar información para alcanzar esa extensión.

Elige UNA categoría correcta de esta lista:
{", ".join(CATEGORIAS)}

No clasifiques una noticia local como internacional.
No clasifiques una noticia deportiva en Colombia si
su tema principal es el deporte.

Devuelve exclusivamente JSON válido con esta estructura:

{{
  "descartar": false,
  "titulo": "Título original",
  "resumen": "Resumen de la noticia",
  "categoria": "Categoría",
  "contenido": "Artículo completo con párrafos separados",
  "descripcion_instagram": "Descripción breve, fiel a los hechos y preparada para Instagram"
}}
"""

    respuesta = cliente.chat.completions.create(
        model=MODELO,
        messages=[{"role": "user", "content": instrucciones}],
        temperature=0.2,
        reasoning_format="hidden",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "articulo_periodistico",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "descartar": {"type": "boolean"},
                        "titulo": {"type": "string"},
                        "resumen": {"type": "string"},
                        "categoria": {
                            "type": "string",
                            "enum": CATEGORIAS
                        },
                        "contenido": {"type": "string"},
                        "descripcion_instagram": {"type": "string"}
                    },
                    "required": [
                        "descartar",
                        "titulo",
                        "resumen",
                        "categoria",
                        "contenido",
                        "descripcion_instagram"
                    ],
                    "additionalProperties": False
                }
            }
        }
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
    resumen = str(articulo.get("resumen", "")).strip()
    contenido = str(articulo.get("contenido", "")).strip()

    if not titulo or not resumen:
        return None

    if len(contenido.split()) < 250:
        print("Artículo demasiado corto.")
        return None

    return {
        "titulo": titulo,
        "resumen": resumen,
        "categoria": articulo["categoria"],
        "contenido": contenido,
        "descripcion_instagram": str(articulo.get("descripcion_instagram", "")).strip()
    }



def crear_portada_instagram(identificador, titulo, categoria):
    carpeta = SITE / "social"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{identificador}.jpg"
    imagen = Image.new("RGB", (1080, 1080), "#171717")
    d = ImageDraw.Draw(imagen)
    try:
        grande = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 72)
        pequena = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except OSError:
        grande = ImageFont.load_default()
        pequena = ImageFont.load_default()
    d.rectangle((0, 0, 1080, 18), fill="#b5282f")
    d.text((75, 75), "CEV NOTICIAS", font=pequena, fill="white")
    d.text((75, 150), str(categoria).upper()[:35], font=pequena, fill="#e14a50")
    lineas, actual = [], ""
    for palabra in str(titulo).split():
        prueba = (actual + " " + palabra).strip()
        if d.textbbox((0, 0), prueba, font=grande)[2] > 920 and actual:
            lineas.append(actual)
            actual = palabra
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    y = 300
    for linea in lineas[:6]:
        d.text((75, y), linea, font=grande, fill="white")
        y += 105
    d.line((75, 930, 1005, 930), fill="#b5282f", width=5)
    d.text((75, 960), "PERIODISMO · CONTEXTO · ACTUALIDAD", font=pequena, fill="#c9c6c0")
    imagen.save(ruta, "JPEG", quality=90, optimize=True)
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
    Completa los datos de Instagram de noticias antiguas que ya están
    publicadas en la web. Si no existe una imagen con licencia verificada,
    utiliza una portada gráfica propia de CEV NOTICIAS.
    """
    portadas_creadas = 0
    descripciones_creadas = 0

    for noticia in noticias:
        if not isinstance(noticia, dict):
            continue

        identificador = str(noticia.get("id", "")).strip()
        titulo = str(noticia.get("titulo", "")).strip()
        if not identificador or not titulo:
            continue

        imagen_instagram = str(noticia.get("imagen_instagram", "")).strip()
        tipo_imagen = str(noticia.get("imagen_instagram_tipo", "")).strip()

        if not imagen_instagram:
            noticia["imagen_instagram"] = crear_portada_instagram(
                identificador,
                titulo,
                noticia.get("categoria", "Actualidad")
            )
            noticia["imagen_instagram_tipo"] = "grafica_propia"
            portadas_creadas += 1
        elif not tipo_imagen:
            # No se presume que una foto externa tenga licencia.
            # Las imágenes antiguas sin metadatos se sustituyen por una
            # portada gráfica propia para evitar reutilización no autorizada.
            noticia["imagen_instagram"] = crear_portada_instagram(
                identificador,
                titulo,
                noticia.get("categoria", "Actualidad")
            )
            noticia["imagen_instagram_tipo"] = "grafica_propia"
            portadas_creadas += 1

        if not str(noticia.get("descripcion_instagram", "")).strip():
            noticia["descripcion_instagram"] = crear_caption_instagram(
                noticia,
                noticia.get("imagen_credito") or {}
            )
            descripciones_creadas += 1

    print(
        "Preparación Instagram: "
        f"{portadas_creadas} portadas propias y "
        f"{descripciones_creadas} descripciones completadas."
    )


def ejecutar():
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No está configurada la clave GROQ_API_KEY."
        )

    cliente = Groq(api_key=api_key)

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

    print("Grupos temáticos encontrados:", len(grupos))

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

    for grupo in grupos:
        if len(nuevas) >= MAX_ARTICULOS_POR_EJECUCION:
            break

        if solicitudes_groq >= MAX_SOLICITUDES_DIARIAS:
            print("Límite diario de seguridad alcanzado. Se detiene la generación.")
            break

        fuentes = leer_contenidos(grupo)

        dominios = {
            urlparse(f["url"]).netloc.lower()
            for f in fuentes
        }

        # Se permite publicar con una sola fuente.
        # Si hay varias, se contrastan; si hay una, se usa
        # únicamente la información recuperada de ese medio.
        if len(fuentes) < 1:
            print("Noticia sin contenido recuperable:", grupo["titulo"])
            continue

        try:
            solicitudes_groq += 1
            articulo = generar_articulo(
                cliente,
                grupo["titulo"],
                fuentes
            )

            if not articulo:
                continue

            identificador = identificador_articulo(
                articulo["titulo"]
            )

            if any(
                n.get("id") == identificador
                for n in publicadas + nuevas
            ):
                continue

            # Se priorizan bancos de imágenes con licencias reutilizables.
            # Las imágenes RSS/de medios no se reutilizan automáticamente,
            # porque podrían tener derechos reservados.
            imagen_info = buscar_imagen(
                articulo["titulo"],
                articulo["resumen"],
                articulo["categoria"]
            )

            portada_instagram = crear_portada_instagram(identificador, articulo["titulo"], articulo["categoria"])
            caption_instagram = crear_caption_instagram(articulo, imagen_info)

            nuevas.append({
                "id": identificador,
                "titulo": articulo["titulo"],
                "resumen": articulo["resumen"],
                "categoria": articulo["categoria"],
                "contenido": articulo["contenido"],
                "imagen": imagen_info.get("url", "") if imagen_info else "",
                "imagen_credito": imagen_info if imagen_info else {},
                "imagen_instagram": imagen_info.get("url") if imagen_info else portada_instagram,
                "imagen_instagram_tipo": "externa_con_licencia" if imagen_info else "grafica_propia",
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
                    {
                        "nombre": fuente["nombre"]
                    }
                    for fuente in fuentes
                ]
            })

            print("Artículo creado:", articulo["titulo"])
            time.sleep(2)

        except Exception as error:
            mensaje_error = str(error)
            print("Error al generar artículo:", mensaje_error)

            print("Se detienen los intentos para evitar repetir errores de API.")
            break

    resultado = nuevas + publicadas
    resultado = resultado[:MAX_ARTICULOS_ANTERIORES]

    # Completa también las noticias que ya estaban en la web para que
    # puedan entrar a la cola de Instagram sin esperar a nuevos artículos.
    asegurar_datos_instagram(resultado)

    guardar_json(CACHE, {
        "noticias": resultado,
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
