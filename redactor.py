
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
AUTOMATION_STATE = os.path.join(BASE, "automation_state.json")

MODELO = "openai/gpt-oss-20b"
MAX_NOTICIAS = 20
MAX_ARTICULOS_POR_EJECUCION = 5
MAX_ARTICULOS_DIARIOS = 30
MAX_SOLICITUDES_POR_EJECUCION = 5
MAX_GRUPOS_REVISADOS_POR_EJECUCION = 36
MINUTOS_ENTRE_SOLICITUDES = 20
MAX_SOLICITUDES_DIARIAS = 60
MAX_FUENTES_POR_ARTICULO = 4
MAX_CARACTERES_POR_FUENTE = 9000
MAX_TITULARES_POR_CATEGORIA = 10
MAX_EDAD_TITULARES_HORAS = 72
MAX_ARTICULOS_ANTERIORES = 150
MAX_EDAD_HORAS = 72
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

    return None


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
    estado_fuentes = []
    limite = datetime.now(timezone.utc) - timedelta(hours=MAX_EDAD_HORAS)

    for feed in configuracion:
        url_feed = str(feed.get("url", "")).strip()
        nombre = str(feed.get("nombre", "Fuente")).strip()
        zona = str(feed.get("zona", "Nacional / internacional")).strip()
        consulta = datetime.now(timezone.utc).isoformat()

        if not url_feed:
            estado_fuentes.append({
                "nombre": nombre,
                "url": "",
                "zona": zona,
                "estado": "error",
                "entradas_rss": 0,
                "titulares_vigentes": 0,
                "ultima_consulta": consulta,
                "error": "La fuente no tiene una URL configurada."
            })
            continue

        try:
            respuesta = requests.get(
                url_feed,
                headers=CABECERAS,
                timeout=20
            )
            respuesta.raise_for_status()
            datos = feedparser.parse(respuesta.content)
            titulares_vigentes = 0

            if not datos.entries:
                print("RSS sin noticias:", nombre)
                estado_fuentes.append({
                    "nombre": nombre,
                    "url": url_feed,
                    "zona": zona,
                    "estado": "sin_entradas",
                    "entradas_rss": 0,
                    "titulares_vigentes": 0,
                    "ultima_consulta": consulta,
                    "error": "La respuesta no contiene entradas RSS/Atom."
                })
                continue

            print(
                f"Fuente disponible: {nombre} "
                f"({len(datos.entries)} entradas)"
            )

            for entrada in datos.entries[:40]:
                fecha = fecha_entrada(entrada)

                if fecha is None:
                    print(f"Entrada RSS sin fecha verificable; se omite: {nombre}")
                    continue

                if fecha < limite:
                    continue

                titulo = str(entrada.get("title", "")).strip()
                enlace = str(entrada.get("link", "")).strip()

                if not titulo or not enlace.startswith(("https://", "http://")):
                    continue

                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fuente": nombre,
                    "fecha": fecha.isoformat(),
                    "imagen": url_imagen_entrada(entrada)
                })
                titulares_vigentes += 1

            estado_fuentes.append({
                "nombre": nombre,
                "url": url_feed,
                "zona": zona,
                "estado": "ok",
                "entradas_rss": len(datos.entries),
                "titulares_vigentes": titulares_vigentes,
                "ultima_consulta": consulta,
                "error": ""
            })

        except Exception as error:
            mensaje = f"{type(error).__name__}: {str(error)[:160]}"
            print(f"No se pudo leer {nombre}: {mensaje}")
            estado_fuentes.append({
                "nombre": nombre,
                "url": url_feed,
                "zona": zona,
                "estado": "error",
                "entradas_rss": 0,
                "titulares_vigentes": 0,
                "ultima_consulta": consulta,
                "error": mensaje
            })

    resultados.sort(
        key=lambda noticia: noticia["fecha"],
        reverse=True
    )

    total_ok = sum(1 for f in estado_fuentes if f["estado"] == "ok")
    total_error = sum(1 for f in estado_fuentes if f["estado"] != "ok")
    print(
        f"Total de noticias encontradas en RSS: {len(resultados)} | "
        f"Fuentes activas: {total_ok} | Fuentes con incidencias: {total_error}"
    )
    return resultados, estado_fuentes


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
    if any(nombre in nombres for nombre in ("el tiempo cali", "90 minutos", "diario occidente", "qhubo cali")):
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


def prioridad_de_investigacion(fuente):
    """Ordena primero documentos y comunicados primarios; después, prensa independiente."""
    host = (urlparse(str(fuente.get("url", "")).strip()).hostname or "").lower()
    oficiales = (
        ".gov.co", ".gov", ".gob.es", ".gov.uk", ".gov.au",
        "cali.gov.co", "valledelcauca.gov.co", "emcali.com.co",
        "policia.gov.co", "fiscalia.gov.co", "dane.gov.co",
        "minsalud.gov.co", "mintransporte.gov.co"
    )
    if any(host.endswith(dominio) for dominio in oficiales):
        nivel = 0
    else:
        nivel = 1
    return (nivel, -fecha_a_timestamp(fuente.get("fecha")))


def leer_contenidos(grupo):
    """Recupera hasta cuatro textos completos de dominios distintos para investigar un hecho."""
    fuentes_validas = []
    dominios_leidos = set()
    candidatas = sorted(
        grupo.get("fuentes", []),
        key=prioridad_de_investigacion
    )

    for fuente in candidatas:
        if len(fuentes_validas) >= MAX_FUENTES_POR_ARTICULO:
            break
        url = str(fuente.get("url", "")).strip()
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if not url.startswith("https://") or not host or host in dominios_leidos:
            continue

        texto = extraer_articulo(url)
        if len(texto) < 500:
            print("Texto insuficiente:", fuente.get("fuente"), fuente.get("titulo"))
            continue

        fuentes_validas.append({
            "nombre": str(fuente.get("fuente") or "Fuente consultada"),
            "titulo": str(fuente.get("titulo") or ""),
            "url": url,
            "texto": texto[:MAX_CARACTERES_POR_FUENTE]
        })
        dominios_leidos.add(host)

    print(
        f"Investigación documental: {len(fuentes_validas)} textos recuperados "
        f"de {len(dominios_leidos)} dominios."
    )
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
Eres parte de la mesa de investigación y redacción de CEV NOTICIAS,
un medio digital independiente con prioridad informativa en Cali,
el Valle del Cauca, Colombia y la actualidad internacional.

Tu tarea NO es resumir ni parafrasear el primer titular. Debes producir
una cobertura periodística propia a partir de una investigación documental
que contraste los textos completos disponibles.

TEMA DETECTADO POR EL RADAR:
{titulo_referencia}

MATERIAL DOCUMENTAL RECUPERADO:
{''.join(material)}

MÉTODO DE INVESTIGACIÓN OBLIGATORIO:
1. Identifica el hecho central, su fecha, lugar, protagonistas y qué cambió.
2. Compara los textos: separa hechos coincidentes, datos que solo aporta
   una fuente, versiones oficiales, testimonios atribuidos y contradicciones.
3. Busca un enfoque periodístico útil para el lector de CEV NOTICIAS.
   No reproduzcas la estructura ni el orden de los artículos consultados.
4. Añade contexto comprobable que ayude a entender las consecuencias,
   antecedentes inmediatos, alcance local o nacional y próximos pasos.
5. Explica qué se sabe y qué todavía no está confirmado. Si faltan datos
   importantes, dilo de manera explícita y no los rellenes.
6. Si las fuentes solo repiten el mismo comunicado, no las presentes como
   confirmaciones independientes.
7. Si solo hay un texto recuperado, solo puedes elaborar una nota breve
   de servicio o información atribuida cuando el documento sea primario
   y verificable. Para sucesos sensibles o acusaciones, descarta.
8. Si el material no permite responder qué ocurrió, dónde, cuándo y por
   qué importa, devuelve "descartar": true.

REGLAS DE AUTORÍA Y EXACTITUD:
- Redacta desde cero en español colombiano, con voz periodística natural.
- El artículo debe aportar contexto, explicación y datos, no solo cambiar
  palabras del material fuente.
- No inventes cifras, nombres, declaraciones, causas, responsables,
  reacciones, antecedentes ni consecuencias.
- No inventes citas textuales. Parafrasea con atribución clara.
- Distingue entre lo que afirma una autoridad y lo que está verificado
  por otras fuentes.
- No conviertas una denuncia, hipótesis o versión preliminar en hecho.
- Evita adjetivos sensacionalistas que alteren el sentido de los hechos.
- No incluyas publicidad, frases de relleno ni conclusiones genéricas.
- No incluyas enlaces dentro del cuerpo del artículo; las referencias
  se adjuntan en el apartado de fuentes del sitio.

ESTRUCTURA DEL ARTÍCULO:
- Extensión orientativa: 400 a 600 palabras, solo si el material lo permite.
- Entre 6 y 9 párrafos sustanciales, con una idea útil en cada uno.
- Apertura: el hecho y la novedad principal, sin rodeos.
- Desarrollo: datos concretos, versiones atribuidas, contraste y cronología.
- Contexto: por qué importa para los habitantes o para el país.
- Cierre: qué falta por conocerse, qué sigue o cuál es el estado actual.
- No repitas el resumen en el primer párrafo.

CATEGORÍA:
Elige UNA de estas categorías:
{", ".join(CATEGORIAS)}
- "Cali": el hecho ocurre principalmente en Santiago de Cali.
- "Valle del Cauca": ocurre en otro municipio del departamento.
- "Colombia": ocurre en otra región del país o tiene alcance nacional.
- "Internacional": ocurre fuera de Colombia.
- No clasifiques una noticia local como internacional o nacional.
- No clasifiques una noticia deportiva general como actualidad de Colombia.

ESTADO DE LA INFORMACIÓN:
- "confirmada": hechos centrales corroborados y sin contradicciones relevantes.
- "en_desarrollo": el acontecimiento sigue ocurriendo o el balance puede cambiar.
- "informacion_preliminar": los datos son iniciales o están sujetos a verificación.
Atribuye las afirmaciones que no estén confirmadas.

Devuelve exclusivamente JSON válido con esta estructura:
{{
  "descartar": false,
  "titulo": "Titular propio, preciso y atractivo",
  "titular_instagram": "Titular breve, llamativo y fiel a los hechos",
  "resumen": "Resumen propio que explique el hecho y su relevancia",
  "categoria": "Categoría",
  "estado_informacion": "confirmada | en_desarrollo | informacion_preliminar",
  "enfoque_original": "Qué aporta esta cobertura de CEV frente a la información inicial, con datos concretos",
  "hechos_clave": ["Hecho verificable 1", "Hecho verificable 2", "Hecho verificable 3"],
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

    palabras_articulo = len(contenido.split())
    parrafos = [p.strip() for p in contenido.split("\\n\\n") if p.strip()]
    enfoque_original = str(articulo.get("enfoque_original", "")).strip()
    hechos_clave = articulo.get("hechos_clave", [])
    hechos_clave = [
        str(hecho).strip() for hecho in hechos_clave
        if str(hecho).strip()
    ] if isinstance(hechos_clave, list) else []

    if palabras_articulo < 380:
        print(f"Artículo descartado: solo {palabras_articulo} palabras; mínimo 380.")
        return None
    if len(parrafos) < 5:
        print(f"Artículo descartado: solo {len(parrafos)} párrafos sustanciales.")
        return None
    if len(enfoque_original) < 45 or len(hechos_clave) < 3:
        print("Artículo descartado: no explica su aporte original o no identifica tres hechos clave.")
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
        "enfoque_original": enfoque_original,
        "hechos_clave": hechos_clave[:6],
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
        elif licencia_apta:
            noticia["imagen_instagram"] = imagen_actual
            noticia["imagen_instagram_tipo"] = "externa_con_licencia"
        elif noticia.get("imagen_busqueda_intentada") and not noticia.get("imagen_instagram"):
            noticia["imagen_instagram"] = crear_portada_instagram(
                identificador,
                noticia.get("titular_instagram") or titulo,
                noticia.get("categoria", ""),
                ""
            )
            noticia["imagen_instagram_tipo"] = "portada_grafica_cev"

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
    if "90 minutos" in fuente or "diario occidente" in fuente or "qhubo cali" in fuente:
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

    entradas, estado_fuentes = obtener_fuentes()
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

    estado_automatizacion = leer_json(AUTOMATION_STATE, {})
    if not isinstance(estado_automatizacion, dict):
        estado_automatizacion = {}

    # Los contadores viven en un archivo separado para que un borrador
    # descartado nunca reinicie el límite diario ni el intervalo del modelo.
    if estado_automatizacion.get("fecha_solicitudes_groq") == fecha_control:
        solicitudes_groq = int(estado_automatizacion.get("solicitudes_groq", 0))
    elif cache.get("fecha_solicitudes_groq") == fecha_control:
        solicitudes_groq = int(cache.get("solicitudes_groq", 0))
    else:
        solicitudes_groq = 0

    if estado_automatizacion.get("fecha_articulos_dia") == fecha_control:
        articulos_hoy = int(estado_automatizacion.get("articulos_generados_dia", 0))
    else:
        articulos_hoy = 0

    print(
        f"Solicitudes Groq usadas hoy: {solicitudes_groq}/"
        f"{MAX_SOLICITUDES_DIARIAS}"
    )
    print(
        f"Artículos originales generados hoy: {articulos_hoy}/"
        f"{MAX_ARTICULOS_DIARIOS}"
    )

    ultima_solicitud_groq = (
        estado_automatizacion.get("ultima_solicitud_groq")
        or cache.get("ultima_solicitud_groq", "")
    )
    timestamp_ultima = fecha_a_timestamp(ultima_solicitud_groq)
    ahora_ts = datetime.now(timezone.utc).timestamp()
    puede_generar = (
        bool(cliente)
        and solicitudes_groq < MAX_SOLICITUDES_DIARIAS
        and articulos_hoy < MAX_ARTICULOS_DIARIOS
    )

    if puede_generar and timestamp_ultima and (ahora_ts - timestamp_ultima) < MINUTOS_ENTRE_SOLICITUDES * 60:
        puede_generar = False
        print("Pausa de consumo activa: los titulares RSS sí se actualizan en este ciclo.")
    if solicitudes_groq >= MAX_SOLICITUDES_DIARIAS:
        print("Cupo diario de solicitudes del modelo agotado. Se mantienen los titulares RSS.")
    if articulos_hoy >= MAX_ARTICULOS_DIARIOS:
        print("Cupo diario de artículos originales agotado. Se mantienen los titulares RSS.")

    grupos_revisados = 0
    solicitudes_esta_ejecucion = 0

    if puede_generar:
        for grupo in grupos:
            if len(nuevas) >= MAX_ARTICULOS_POR_EJECUCION:
                break
            if articulos_hoy + len(nuevas) >= MAX_ARTICULOS_DIARIOS:
                print("Límite diario de artículos alcanzado.")
                break
            if solicitudes_esta_ejecucion >= MAX_SOLICITUDES_POR_EJECUCION:
                break
            if grupos_revisados >= MAX_GRUPOS_REVISADOS_POR_EJECUCION:
                print("Límite de grupos revisados en esta ejecución alcanzado.")
                break

            grupos_revisados += 1
            fuentes = leer_contenidos(grupo)
            # Solo se admiten fuentes HTTPS con dominio real y texto extraído.
            fuentes = [
                fuente for fuente in fuentes
                if urlparse(str(fuente.get("url", ""))).scheme == "https"
                and urlparse(str(fuente.get("url", ""))).hostname
                and len(str(fuente.get("texto", "")).strip()) >= 500
                and str(fuente.get("nombre", "")).strip()
            ]

            dominios = {
                urlparse(f["url"]).hostname.lower()
                for f in fuentes
            }

            if not dominios:
                print("Noticia descartada: no tiene una fuente HTTPS comprobable:", grupo["titulo"])
                continue

            texto_revision = (str(grupo.get("titulo", "")) + " " + " ".join(
                str(f.get("texto", "")) for f in fuentes
            )).lower()
            temas_sensibles = re.search(
                r"\b(accidente|muert[eo]|falleci|homicid|asesinat|robo|hurto|captura|detenid|denuncia|acusaci[oó]n|víctim|victim|agresi[oó]n|desaparici[oó]n|abuso|corrupci[oó]n)\w*",
                texto_revision
            )
            if temas_sensibles and len(dominios) < 2:
                print("Noticia sensible descartada: requiere dos fuentes independientes:", grupo["titulo"])
                continue

            try:
                if solicitudes_esta_ejecucion > 0:
                    print("Pausa de 65 segundos entre llamadas de generación.")
                    time.sleep(65)

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

                datos_imagen_obligatorios = ("url", "autor", "fuente", "pagina", "licencia", "licencia_url")
                if not imagen_info or not all(str(imagen_info.get(campo, "")).strip() for campo in datos_imagen_obligatorios):
                    print("No hay fotografía con licencia y atribución completas; la noticia se publicará sin foto:", articulo["titulo"])
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
                    "autor": "CEV NOTICIAS",
                    "titulo": articulo["titulo"],
                    "titular_instagram": articulo.get("titular_instagram") or articulo["titulo"],
                    "resumen": articulo["resumen"],
                    "categoria": articulo["categoria"],
                    "contenido": articulo["contenido"],
                    "estado_informacion": articulo.get("estado_informacion", "confirmada"),
                    "investigacion": {
                        "enfoque_original": articulo.get("enfoque_original", ""),
                        "hechos_clave": articulo.get("hechos_clave", []),
                        "fuentes_recuperadas": len(fuentes),
                        "dominios_independientes": len(dominios),
                        "fecha": datetime.now(timezone.utc).isoformat()
                    },
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

            except Exception as error:
                print("Error al generar artículo:", str(error))
                print("Se detiene el intento para respetar el cupo del modelo.")
                break
    else:
        print("En esta ejecución no corresponde consumir una solicitud de Groq.")

    articulos_hoy += len(nuevas)

    # Persistencia independiente: estos contadores no se pierden cuando
    # el workflow descarta un lote editorial por sus validaciones.
    guardar_json(AUTOMATION_STATE, {
        "fecha_solicitudes_groq": fecha_control,
        "solicitudes_groq": solicitudes_groq,
        "ultima_solicitud_groq": ultima_solicitud_groq,
        "fecha_articulos_dia": fecha_control,
        "articulos_generados_dia": articulos_hoy,
        "limite_articulos_diario": MAX_ARTICULOS_DIARIOS,
        "limite_solicitudes_diario": MAX_SOLICITUDES_DIARIAS,
        "limite_articulos_ejecucion": MAX_ARTICULOS_POR_EJECUCION
    })

    resultado = nuevas + publicadas
    resultado = resultado[:MAX_ARTICULOS_ANTERIORES]

    # Completa también las noticias que ya estaban en la web para que
    # puedan entrar a la cola de Instagram sin esperar a nuevos artículos.
    asegurar_datos_instagram(resultado)

    guardar_json(CACHE, {
        "noticias": resultado,
        "titulares_rss": titulares_rss,
        "estado_fuentes": estado_fuentes,
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
