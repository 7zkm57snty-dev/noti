import os
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "cache.json")
STATE = os.path.join(BASE, "buffer_publicados.json")

TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN")
CHANNEL_ID = "6ae80f3ce29c69a171328e5d"
BUFFER_API = "https://api.buffer.com"
MAX_PUBLICACIONES_POR_DIA = 4
MAX_PUBLICACIONES_POR_EJECUCION = 1
TZ_COLOMBIA = timezone(timedelta(hours=-5))

LICENCIAS_VALIDAS = ("cc0", "cc-by", "cc-by-sa", "public domain", "publicdomain", "pdm")


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


def fecha_local():
    return datetime.now(TZ_COLOMBIA)


def licencia_valida(info):
    licencia = str(info.get("licencia", "")).lower()
    if not any(item in licencia for item in LICENCIAS_VALIDAS):
        return False
    if "nc" in licencia or "nd" in licencia:
        return False
    return bool(info.get("pagina") and info.get("licencia_url"))


def articulo_apto(noticia):
    imagen = str(noticia.get("imagen_instagram", "")).strip()
    if not imagen.startswith("https://"):
        return False, "no tiene imagen apta para Instagram"
    tipo_imagen = str(noticia.get("imagen_instagram_tipo", ""))
    if tipo_imagen != "grafica_propia":
        info = noticia.get("imagen_credito") or {}
        if not licencia_valida(info):
            return False, "no tiene licencia y atribución verificables"
    fuentes = noticia.get("fuentes") or []
    nombres = {str(f.get("nombre", "")).strip().lower() for f in fuentes if f.get("nombre")}
    titulo = str(noticia.get("titulo", "")).lower()
    sensibles = ("homicidio", "asesinato", "accidente", "captura", "robo", "hurto", "denuncia", "víctima", "muerto", "herido", "corrupción", "controversia")
    if any(p in titulo for p in sensibles) and len(nombres) < 2:
        return False, "tema sensible sin corroboración adicional"
    if not nombres:
        return False, "no tiene fuente identificada"
    identificador = str(noticia.get("id", "")).strip()
    if not identificador:
        return False, "no tiene identificador"
    return True, ""


def construir_texto(noticia):
    titulo = str(noticia.get("titulo", "")).strip()
    resumen = str(noticia.get("resumen", "")).strip()
    categoria = str(noticia.get("categoria", "")).strip()
    identificador = str(noticia["id"])
    url_articulo = f"https://cevnoticias.com/notas/{identificador}.html"
    info = noticia.get("imagen_credito") or {}

    autor = str(info.get("autor") or "Autor no identificado").strip()
    fuente = str(info.get("fuente") or "Repositorio de imágenes").strip()
    licencia = str(info.get("licencia") or "").strip()
    pagina = str(info.get("pagina") or "").strip()
    licencia_url = str(info.get("licencia_url") or "").strip()

    texto = str(noticia.get("descripcion_instagram") or f"{titulo}\n\n{resumen}\n\nLee la noticia completa en cevnoticias.com.")
    return texto


def crear_publicacion(noticia):
    texto = construir_texto(noticia)
    imagen = noticia["imagen_instagram"]

    # Los valores de texto se codifican como literales GraphQL para evitar
    # errores por comillas, saltos de línea o caracteres especiales.
    query = """
    mutation CreateQueuedPost {
      createPost(input: {
        text: %s,
        channelId: "%s",
        schedulingType: automatic,
        mode: addToQueue,
        saveToDraft: false,
        assets: [{ image: { url: %s } }],
        metadata: {
          instagram: {
            type: post,
            shouldShareToFeed: true
          }
        }
      }) {
        ... on PostActionSuccess {
          post { id text }
        }
        ... on MutationError { message }
      }
    }
    """ % (
        json.dumps(texto, ensure_ascii=False),
        CHANNEL_ID,
        json.dumps(imagen)
    )

    respuesta = requests.post(
        BUFFER_API,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        },
        json={"query": query},
        timeout=40
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    if datos.get("errors"):
        raise RuntimeError("Error GraphQL de Buffer: " + str(datos["errors"]))

    resultado = (datos.get("data") or {}).get("createPost") or {}
    if resultado.get("post"):
        return resultado["post"]
    if resultado.get("message"):
        raise RuntimeError("Buffer rechazó la publicación: " + resultado["message"])
    raise RuntimeError("Respuesta inesperada de Buffer: " + str(datos))


def ejecutar():
    if not TOKEN:
        raise SystemExit("Falta el secreto BUFFER_ACCESS_TOKEN.")

    cache = leer_json(CACHE, {"noticias": []})
    noticias = cache.get("noticias", []) if isinstance(cache, dict) else []
    estado = leer_json(STATE, {"publicaciones": [], "fecha": ""})
    if not isinstance(estado, dict):
        estado = {"publicaciones": [], "fecha": ""}

    hoy = fecha_local().strftime("%Y-%m-%d")
    if estado.get("fecha") != hoy:
        estado["fecha"] = hoy
        estado["publicaciones_hoy"] = 0

    publicaciones = estado.get("publicaciones", [])
    ids_publicados = {str(x.get("noticia_id")) for x in publicaciones}
    hechas_hoy = int(estado.get("publicaciones_hoy", 0))

    if hechas_hoy >= MAX_PUBLICACIONES_POR_DIA:
        print(f"Tope diario alcanzado: {hechas_hoy}/{MAX_PUBLICACIONES_POR_DIA}.")
        guardar_json(STATE, estado)
        return

    creadas = 0
    for noticia in noticias:
        if creadas >= MAX_PUBLICACIONES_POR_EJECUCION:
            break
        noticia_id = str(noticia.get("id", ""))
        if not noticia_id or noticia_id in ids_publicados:
            continue

        apto, motivo = articulo_apto(noticia)
        if not apto:
            print(f"Se omite {noticia.get('titulo', noticia_id)}: {motivo}.")
            continue

        post = crear_publicacion(noticia)
        publicaciones.append({
            "noticia_id": noticia_id,
            "buffer_post_id": post.get("id", ""),
            "titulo": noticia.get("titulo", ""),
            "fecha": fecha_local().isoformat()
        })
        ids_publicados.add(noticia_id)
        hechas_hoy += 1
        creadas += 1
        print("PUBLICACIÓN AÑADIDA A LA COLA AUTOMÁTICA DE BUFFER.")
        print("Noticia:", noticia.get("titulo", ""))
        print("Post ID:", post.get("id", ""))

    estado["publicaciones"] = publicaciones[-500:]
    estado["publicaciones_hoy"] = hechas_hoy
    estado["fecha"] = hoy
    guardar_json(STATE, estado)
    print(f"Publicaciones añadidas en esta ejecución: {creadas}.")
    print(f"Publicaciones añadidas hoy: {hechas_hoy}/{MAX_PUBLICACIONES_POR_DIA}.")
    print("Buffer publicará según los horarios configurados en la cola del canal.")


if __name__ == "__main__":
    ejecutar()
