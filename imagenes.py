import html
import re
import requests
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": "CEVNoticias/1.0 (https://cevnoticias.com; contacto editorial)",
    "Accept": "application/json,image/*,*/*"
}
LICENCIAS_PERMITIDAS = {
    "cc0", "cc-by", "cc-by-sa", "publicdomain", "public-domain",
    "pdm", "cc-zero"
}
STOPWORDS = {
    "para", "desde", "sobre", "entre", "tras", "cuando", "donde",
    "porque", "como", "esta", "este", "estos", "estas", "tambien",
    "contra", "despues", "antes", "hacia", "hasta", "ante", "sera",
    "fue", "son", "los", "las", "una", "uno", "del", "por", "con",
    "sin", "que", "sus", "mas", "hoy", "ayer", "nuevo", "nueva",
    "colombia", "noticia", "noticias"
}


def consultas_imagen(titulo, resumen="", categoria=""):
    texto = f"{titulo} {resumen}"
    palabras = re.findall(r"[a-záéíóúñü0-9]{3,}", texto.lower())
    unicas = []
    for palabra in palabras:
        if palabra not in STOPWORDS and palabra not in unicas:
            unicas.append(palabra)

    consulta_tema = " ".join(unicas[:6]).strip()
    consultas = []
    if consulta_tema:
        consultas.append(consulta_tema)
    if categoria:
        consultas.append(f"{' '.join(unicas[:4])} {categoria}".strip())
    if categoria and categoria.lower() in ("cali", "valle del cauca"):
        consultas.extend([
            f"{' '.join(unicas[:5])} Cali Colombia",
            f"{' '.join(unicas[:4])} Valle del Cauca Colombia"
        ])
    if re.search(r"carrera|corredor|atlet|ciclis|f[uú]tbol|baloncesto|partido|deport|estadio|marat[oó]n", texto, re.I):
        consultas.append(f"{' '.join(unicas[:4])} sports running football competition")
    if re.search(r"planetario|astronom|cosmos|telescopio|espacio|cohete|sat[eé]lite", texto, re.I):
        consultas.append(f"{' '.join(unicas[:4])} planetarium astronomy space")
    if re.search(r"sismo|temblor|terremoto|incendio|rescate|inundaci[oó]n|emergencia", texto, re.I):
        consultas.append(f"{' '.join(unicas[:4])} emergency response rescue")
    if re.search(r"tr[aá]nsito|movilidad|transporte|carretera|v[ií]a", texto, re.I):
        consultas.append(f"{' '.join(unicas[:4])} road traffic transport")

    resultado = []
    for consulta in consultas:
        consulta = consulta.strip()
        if len(consulta) >= 8 and consulta not in resultado:
            resultado.append(consulta)
    return resultado[:4]


def comprobar_imagen(url):
    if not url or not url.startswith("https://"):
        return False
    try:
        respuesta = requests.get(
            url, headers=HEADERS, timeout=5, stream=True,
            allow_redirects=True
        )
        tipo = respuesta.headers.get("Content-Type", "").lower()
        longitud = int(respuesta.headers.get("Content-Length", "0") or 0)
        valido = respuesta.status_code == 200 and "image/" in tipo
        # Evita descartar fotografías pequeñas válidas por un umbral excesivo.
        if longitud and longitud < 2048:
            valido = False
        respuesta.close()
        return valido
    except requests.RequestException:
        return False


def buscar_commons(consulta):
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{consulta} filetype:bitmap",
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1200,
        "format": "json"
    }
    try:
        respuesta = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params, headers=HEADERS, timeout=8
        )
        respuesta.raise_for_status()
        paginas = respuesta.json().get("query", {}).get("pages", {})
        for pagina in paginas.values():
            info = (pagina.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            licencia = html.unescape(meta.get("LicenseShortName", {}).get("value", ""))
            licencia_url = meta.get("LicenseUrl", {}).get("value", "")
            licencia_key = re.sub(r"[^a-z0-9-]", "", licencia.lower())
            if not any(x in licencia_key for x in ("ccby", "cc-by", "cc0", "publicdomain", "public-domain")):
                continue
            if "nc" in licencia_key or "nd" in licencia_key:
                continue
            imagen = info.get("thumburl") or info.get("url", "")
            pagina_url = info.get("descriptionurl", "")
            autor = html.unescape(meta.get("Artist", {}).get("value", "Autor no identificado"))
            if "<" in autor:
                autor = re.sub(r"<[^>]+>", "", autor).strip()
            if imagen and comprobar_imagen(imagen):
                return {
                    "url": imagen,
                    "autor": autor or "Autor no identificado",
                    "fuente": "Wikimedia Commons",
                    "pagina": pagina_url,
                    "licencia": licencia or "Consultar ficha",
                    "licencia_url": licencia_url,
                    "tipo": "fotografía de archivo"
                }
    except (requests.RequestException, ValueError, KeyError) as error:
        print("Búsqueda en Wikimedia Commons fallida:", error)
    return None


def buscar_openverse(consulta):
    params = {
        "q": consulta,
        "page_size": 8,
        "license_type": "commercial",
        "mature": "false"
    }
    try:
        respuesta = requests.get(
            "https://api.openverse.org/v1/images/",
            params=params, headers=HEADERS, timeout=18
        )
        respuesta.raise_for_status()
        for item in respuesta.json().get("results", []):
            licencia = (item.get("license") or "").lower()
            if licencia not in LICENCIAS_PERMITIDAS:
                continue
            imagen = item.get("url", "")
            if not comprobar_imagen(imagen):
                continue
            return {
                "url": imagen,
                "autor": item.get("creator") or "Autor no identificado",
                "fuente": f"Openverse ({item.get('source') or item.get('provider') or 'archivo'})",
                "pagina": item.get("foreign_landing_url") or item.get("detail_url", ""),
                "licencia": f"{licencia.upper()} {item.get('license_version') or ''}".strip(),
                "licencia_url": item.get("license_url", ""),
                "tipo": "fotografía de archivo"
            }
    except (requests.RequestException, ValueError, KeyError) as error:
        print("Búsqueda en Openverse fallida:", error)
    return None


def buscar_imagen(titulo, resumen="", categoria=""):
    consultas = consultas_imagen(titulo, resumen, categoria)
    for consulta in consultas:
        print("Buscando imagen en Wikimedia Commons:", consulta)
        imagen = buscar_commons(consulta)
        if imagen:
            print("Imagen encontrada en Wikimedia Commons.")
            return imagen

    for consulta in consultas:
        print("Alternativa: buscando en Openverse:", consulta)
        imagen = buscar_openverse(consulta)
        if imagen:
            print("Imagen encontrada en Openverse.")
            return imagen

    print("No se encontró imagen reutilizable y comprobada.")
    return None
