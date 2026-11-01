
import os
import re
import json
import time
import hashlib
import requests
import trafilatura
import feedparser

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from google import genai
from google.genai import types

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache.json")
FEEDS = os.path.join(BASE, "feeds.json")

MODELO = "gemini-2.5-flash"
MAX_NOTICIAS = 28
MIN_CONTENIDO_FUENTE = 700
MAX_EDAD_HORAS = 72

CATEGORIAS = [
    "Cali",
    "Valle del Cauca",
    "Colombia",
    "Internacional",
    "Deportes",
    "Tecnología",
    "Economía"
]

CLAVES = {
    "Cali": [
        "cali", "alcaldía de cali", "concejo de cali",
        "emcali", "mio", "valle del lili", "jamundí",
        "yumbo", "palmira"
    ],
    "Valle del Cauca": [
        "valle del cauca", "gobernación del valle",
        "buenaventura", "tuluá", "buga", "cartago",
        "caicedonia", "roldanillo", "zarzal"
    ],
    "Deportes": [
        "fútbol", "futbol", "liga", "partido", "gol",
        "deportivo cali", "américa de cali", "selección",
        "mundial", "deportes", "tenis", "ciclismo",
        "baloncesto", "atletismo"
    ],
    "Tecnología": [
        "tecnología", "tecnologico", "inteligencia artificial",
        "software", "ciberseguridad", "internet", "celular",
        "aplicación", "computador", "robot", "innovación"
    ],
    "Economía": [
        "economía", "inflación", "dólar", "peso colombiano",
        "empleo", "desempleo", "banco", "empresas",
        "inversión", "exportación", "importación", "petróleo"
    ]
}

def leer_json(ruta, defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return defecto


def guardar_json(ruta, datos):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def fecha_entrada(entry):
    try:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        try:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


def obtener_fuentes():
    configuracion = leer_json(FEEDS, [])
    if isinstance(configuracion, dict):
        configuracion = configuracion.get("feeds", [])

    resultados = []
    limite = datetime.now(timezone.utc) - timedelta(hours=MAX_EDAD_HORAS)

    for feed in configuracion:
        url_feed = feed.get("url")
        nombre = feed.get("nombre", "Fuente")
        if not url_feed:
            continue

        try:
            respuesta = requests.get(
                url_feed,
                timeout=20,
                headers={"User-Agent": "CEVNoticias/1.0 (lector RSS)"}
            )
            respuesta.raise_for_status()
            datos = feedparser.parse(respuesta.content)

            for entrada in datos.entries[:30]:
                fecha = fecha_entrada(entrada)
                if fecha < limite:
                    continue

                enlace = entrada.get("link", "")
                titulo = entrada.get("title", "").strip()

                if not enlace.startswith(("https://", "http://")) or not titulo:
                    continue

                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fuente": nombre,
                    "fecha": fecha.isoformat(),
                    "resumen_rss": entrada.get("summary", "")
                })

        except Exception as error:
            print(f"No se pudo leer {nombre}: {error}")

    resultados.sort(key=lambda x: x["fecha"], reverse=True)
    return resultados


def extraer_articulo(url):
    try:
        descargado = trafilatura.fetch_url(url)
        if not descargado:
            return ""

        texto = trafilatura.extract(
            descargado,
            include_comments=False,
            include_tables=False,
            favor_precision=True
        )
        return texto.strip() if texto else ""
    except Exception as error:
        print(f"Error leyendo artículo: {error}")
        return ""


def limpiar_texto(texto):
    texto = re.sub(r"\s+", " ", texto or "")
    return texto.strip()


def identificar_categoria(titulo, textos):
    completo = limpiar_texto(titulo + " " + textos).lower()

    # Los temas específicos tienen prioridad.
    for categoria in ["Deportes", "Tecnología", "Economía"]:
        if any(clave in completo for clave in CLAVES[categoria]):
            return categoria

    if any(clave in completo for clave in CLAVES["Cali"]):
        return "Cali"

    if any(clave in completo for clave in CLAVES["Valle del Cauca"]):
        return "Valle del Cauca"

    return "Colombia"


def clave_similitud(titulo):
    palabras = re.findall(r"[a-záéíóúñ]{4,}", titulo.lower())
    ignorar = {
        "para", "desde", "sobre", "entre", "tras",
        "cuando", "donde", "porque", "según"
    }
    return set(palabras) - ignorar


def duplicada(titulo, anteriores):
    palabras = clave_similitud(titulo)
    if not palabras:
        return False

    for anterior in anteriores:
        otras = clave_similitud(anterior)
        if not otras:
            continue

        similitud = len(palabras & otras) / max(
            1, len(palabras | otras)
        )

        if similitud >= 0.55:
            return True

    return False


def generar_articulo(cliente, candidato):
    fuentes = candidato["fuentes"]

    material = []
    for fuente in fuentes:
        material.append(
            f"""
FUENTE: {fuente['fuente']}
TÍTULO ORIGINAL: {fuente['titulo']}
URL: {fuente['url']}
INFORMACIÓN RECUPERADA:
{fuente['texto'][:6500]}
"""
        )

    instrucciones = f"""
Eres el redactor periodístico de CEV NOTICIAS, un medio digital
independiente dirigido a lectores colombianos.

Redacta un artículo ORIGINAL en español colombiano, utilizando
exclusivamente los hechos respaldados por la información suministrada.

REGLAS OBLIGATORIAS:
1. No copies frases extensas de los medios originales.
2. No inventes cifras, nombres, fechas, declaraciones ni hechos.
3. No presentes una afirmación como confirmada si solo aparece
   en una fuente.
4. Si las fuentes se contradicen, explica la diferencia o descarta
   el dato que no se pueda verificar.
5. No inventes declaraciones entre comillas.
6. No agregues opiniones personales ni especulaciones.
7. Escribe un artículo periodístico desarrollado, no una simple
   paráfrasis de un titular.
8. Si no hay información suficiente para un artículo completo,
   responde con el valor DESCARTAR.
9. Utiliza párrafos claros, subtítulos solo si son necesarios.
10. No incluyas enlaces dentro del cuerpo del artículo.

La noticia debe pertenecer a una de estas secciones:
{", ".join(CATEGORIAS)}

TÍTULOS DE REFERENCIA:
{candidato['titulo']}

INFORMACIÓN DE LAS FUENTES:
{''.join(material)}

Responde únicamente con un objeto JSON válido con esta estructura:
{{
  "titulo": "Título periodístico original",
  "resumen": "Resumen de 2 o 3 frases",
  "categoria": "Una de las secciones permitidas",
  "contenido": "Artículo completo separado por dos saltos de línea"
}}

El artículo debe tener entre 350 y 650 palabras.
Si no existe suficiente información verificable, responde:
DESCARTAR
"""

    respuesta = cliente.models.generate_content(
        model=MODELO,
        contents=instrucciones,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json"
        )
    )

    texto = (respuesta.text or "").strip()
    if not texto:
        return None

    try:
        articulo = json.loads(texto)
    except json.JSONDecodeError:
        return None

    if not isinstance(articulo, dict):
        return None

    if articulo.get("categoria") not in CATEGORIAS:
        return None

    contenido = articulo.get("contenido", "").strip()
    if len(contenido.split()) < 250:
        return None

    if not all(articulo.get(k) for k in ["titulo", "resumen"]):
        return None

    return articulo


def buscar_imagen(candidato):
    # Se evita utilizar fotografías de periódicos sin autorización.
    # La imagen queda vacía si no se dispone de una imagen autorizada.
    return ""


def ejecutar():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta configurar GEMINI_API_KEY en GitHub.")

    cliente = genai.Client(api_key=api_key)

    cache = leer_json(CACHE, {"noticias": []})
    publicadas = cache.get("noticias", [])

    titulos = [n.get("titulo", "") for n in publicadas]

    entradas = obtener_fuentes()
    grupos = {}

    for entrada in entradas:
        titulo = entrada["titulo"]

        if duplicada(titulo, titulos):
            continue

        texto = extraer_articulo(entrada["url"])
        if len(texto) < MIN_CONTENIDO_FUENTE:
            continue

        # Agrupa noticias con títulos parecidos.
        palabras = clave_similitud(titulo)
        clave = hashlib.sha256(
            " ".join(sorted(palabras)).encode("utf-8")
        ).hexdigest()[:16]

        if clave not in grupos:
            grupos[clave] = {
                "titulo": titulo,
                "fuentes": []
            }

        dominio = urlparse(entrada["url"]).netloc.lower()
        if any(
            urlparse(f["url"]).netloc.lower() == dominio
            for f in grupos[clave]["fuentes"]
        ):
            continue

        grupos[clave]["fuentes"].append({
            "fuente": entrada["fuente"],
            "titulo": titulo,
            "url": entrada["url"],
            "texto": texto
        })

    nuevas = []

    for grupo in grupos.values():
        # Se exigen al menos dos medios distintos.
        if len(grupo["fuentes"]) < 2:
            continue

        try:
            articulo = generar_articulo(cliente, grupo)
            if not articulo:
                continue

            categoria = identificar_categoria(
                articulo["titulo"],
                articulo["contenido"]
            )

            # Se respeta la categoría sugerida por el modelo solo
            # cuando pertenece a la lista autorizada.
            if articulo["categoria"] not in CATEGORIAS:
                articulo["categoria"] = categoria

            identificador = hashlib.sha256(
                articulo["titulo"].lower().encode("utf-8")
            ).hexdigest()[:16]

            if identificador in {
                n.get("id") for n in publicadas + nuevas
            }:
                continue

            nuevas.append({
                "id": identificador,
                "titulo": articulo["titulo"],
                "resumen": articulo["resumen"],
                "categoria": articulo["categoria"],
                "contenido": articulo["contenido"],
                "imagen": buscar_imagen(grupo),
                "fecha": datetime.now(
                    timezone(timedelta(hours=-5))
                ).strftime("%d/%m/%Y · %I:%M %p"),
                "fuentes": [
                    {
                        "nombre": f["fuente"],
                        "url": f["url"]
                    }
                    for f in grupo["fuentes"]
                ]
            })

            print("Artículo redactado:", articulo["titulo"])
            time.sleep(2)

        except Exception as error:
            print("No se pudo redactar el artículo:", error)

        if len(nuevas) >= MAX_NOTICIAS:
            break

    resultado = nuevas + publicadas

    # Conserva un máximo de 150 artículos en el historial.
    resultado = resultado[:150]

    guardar_json(CACHE, {
        "noticias": resultado,
        "ultima_actualizacion": datetime.now(
            timezone.utc
        ).isoformat()
    })

    print("Artículos nuevos:", len(nuevas))
    print("Total en archivo:", len(resultado))


if __name__ == "__main__":
    ejecutar()
