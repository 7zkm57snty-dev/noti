
import os
import re
import json
import time
import hashlib
import requests
import feedparser
import trafilatura
from html import unescape

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from google import genai
from google.genai import types

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache.json")
FEEDS = os.path.join(BASE, "feeds.json")

MODELO = "gemini-3.8-flash"
MAX_NOTICIAS = 20
MAX_ARTICULOS_POR_EJECUCION = 1
MAX_SOLICITUDES_DIARIAS = 18
MAX_ARTICULOS_ANTERIORES = 150
MAX_EDAD_HORAS = 168

CATEGORIAS = [
    "Cali",
    "Valle del Cauca",
    "Colombia",
    "Internacional",
    "Deportes",
    "Tecnología",
    "Economía"
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
  "contenido": "Artículo completo con párrafos separados"
}}
"""

    respuesta = cliente.models.generate_content(
        model=MODELO,
        contents=instrucciones,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json"
        )
    )

    if not respuesta.text:
        return None

    try:
        articulo = json.loads(respuesta.text)
    except json.JSONDecodeError:
        print("Gemini devolvió una respuesta no válida.")
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
        "contenido": contenido
    }


def identificador_articulo(titulo):
    return hashlib.sha256(
        titulo.lower().encode("utf-8")
    ).hexdigest()[:16]


def ejecutar():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No está configurada la clave GEMINI_API_KEY."
        )

    cliente = genai.Client(api_key=api_key)

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

    if cache.get("fecha_solicitudes_gemini") != fecha_control:
        solicitudes_gemini = 0
    else:
        solicitudes_gemini = int(cache.get("solicitudes_gemini", 0))

    print(
        f"Solicitudes Gemini usadas hoy: {solicitudes_gemini}/"
        f"{MAX_SOLICITUDES_DIARIAS}"
    )

    for grupo in grupos:
        if len(nuevas) >= MAX_ARTICULOS_POR_EJECUCION:
            break

        if solicitudes_gemini >= MAX_SOLICITUDES_DIARIAS:
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
            solicitudes_gemini += 1
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

            nuevas.append({
                "id": identificador,
                "titulo": articulo["titulo"],
                "resumen": articulo["resumen"],
                "categoria": articulo["categoria"],
                "contenido": articulo["contenido"],
                "imagen": (
                    next(
                        (f.get("imagen", "") for f in grupo["fuentes"] if f.get("imagen")),
                        ""
                    )
                    or obtener_imagen_pagina(fuentes[0]["url"])
                ),
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

            if "429" in mensaje_error or "RESOURCE_EXHAUSTED" in mensaje_error:
                print("Gemini agotó la cuota disponible. Se detienen los intentos.")
                break

    resultado = nuevas + publicadas
    resultado = resultado[:MAX_ARTICULOS_ANTERIORES]

    guardar_json(CACHE, {
        "noticias": resultado,
        "fecha_solicitudes_gemini": fecha_control,
        "solicitudes_gemini": solicitudes_gemini,
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
