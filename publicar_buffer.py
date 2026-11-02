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
ORGANIZATION_ID = "6ae80a08f8da7d9f2595b558"
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


def crear_publicacion(noticia, due_at):
    texto = construir_texto(noticia)
    imagen = noticia["imagen_instagram"]
    query = """
    mutation CreateScheduledPost {
      createPost(input: {
        text: %s,
        channelId: "%s",
        schedulingType: automatic,
        mode: customScheduled,
        dueAt: "%s",
        assets: [{ image: { url: %s } }],
        metadata: {
          instagram: {
            type: post,
            shouldShareToFeed: true
          }
        }
      }) {
        ... on PostActionSuccess {
          post { id text dueAt status channelId }
        }
        ... on MutationError { message }
      }
    }
    """ % (
        json.dumps(texto, ensure_ascii=False),
        CHANNEL_ID,
        due_at,
        json.dumps(imagen)
    )
    return ejecutar_mutacion(query, "createPost")


def editar_publicacion(post_id, noticia, due_at):
    texto = construir_texto(noticia)
    imagen = noticia["imagen_instagram"]
    query = """
    mutation EditScheduledPost {
      editPost(input: {
        id: "%s",
        text: %s,
        dueAt: "%s",
        mode: customScheduled,
        schedulingType: automatic,
        assets: [{ image: { url: %s } }],
        metadata: {
          instagram: {
            type: post,
            shouldShareToFeed: true
          }
        }
      }) {
        ... on PostActionSuccess {
          post { id text dueAt status channelId }
        }
        ... on MutationError { message }
      }
    }
    """ % (
        post_id,
        json.dumps(texto, ensure_ascii=False),
        due_at,
        json.dumps(imagen)
    )
    return ejecutar_mutacion(query, "editPost")


def eliminar_publicacion(post_id):
    query = """
    mutation DeleteScheduledPost {
      deletePost(input: { id: "%s" }) {
        ... on DeletePostSuccess { __typename }
        ... on PostNotDeletableError { message }
        ... on NotFoundError { message }
      }
    }
    """ % post_id
    respuesta = requests.post(
        BUFFER_API,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        },
        json={"query": query},
        timeout=30
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    if datos.get("errors"):
        raise RuntimeError("Error GraphQL al eliminar post: " + str(datos["errors"]))
    resultado = (datos.get("data") or {}).get("deletePost") or {}
    if resultado.get("__typename") == "DeletePostSuccess":
        return True
    if resultado.get("message"):
        raise RuntimeError("Buffer no permitió eliminar el post: " + resultado["message"])
    # La mutación puede devolver una unión con otro campo de éxito vacío.
    if resultado and not resultado.get("message"):
        return True
    raise RuntimeError("Respuesta inesperada al eliminar post: " + str(datos))


def ejecutar_mutacion(query, nombre):
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
    resultado = (datos.get("data") or {}).get(nombre) or {}
    if resultado.get("post"):
        return resultado["post"]
    if resultado.get("message"):
        raise RuntimeError("Buffer rechazó la operación: " + resultado["message"])
    raise RuntimeError("Respuesta inesperada de Buffer: " + str(datos))


def obtener_posts_programados():
    query = """
    query GetScheduledPosts {
      posts(
        first: 100
        input: {
          organizationId: "%s"
          filter: {
            status: [scheduled]
            channelIds: ["%s"]
          }
          sort: [{ field: dueAt, direction: asc }]
        }
      ) {
        edges {
          node {
            id
            text
            dueAt
            status
            channelId
          }
        }
      }
    }
    """ % (ORGANIZATION_ID, CHANNEL_ID)
    respuesta = requests.post(
        BUFFER_API,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        },
        json={"query": query},
        timeout=30
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    if datos.get("errors"):
        raise RuntimeError("Error al consultar la cola de Buffer: " + str(datos["errors"]))
    edges = ((datos.get("data") or {}).get("posts") or {}).get("edges") or []
    return [
        edge.get("node", {})
        for edge in edges
        if edge.get("node", {}).get("id")
    ]


def fecha_noticia(noticia):
    valor = str(noticia.get("fecha", "")).strip()
    for formato in ("%d/%m/%Y · %I:%M %p", "%d/%m/%Y %I:%M %p"):
        try:
            return datetime.strptime(valor, formato).replace(tzinfo=TZ_COLOMBIA)
        except ValueError:
            pass
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return fecha.astimezone(TZ_COLOMBIA) if fecha.tzinfo else fecha.replace(tzinfo=TZ_COLOMBIA)
    except ValueError:
        return None


def similitud_titulos(a, b):
    palabras_a = set(re.findall(r"[a-záéíóúñü]{4,}", str(a).lower()))
    palabras_b = set(re.findall(r"[a-záéíóúñü]{4,}", str(b).lower()))
    comunes = palabras_a & palabras_b
    union = palabras_a | palabras_b
    return len(comunes) / max(1, len(union)) if len(comunes) >= 2 else 0.0


def puntuacion_editorial(noticia, ahora):
    """Prioridad orientativa: actualidad, corroboración y tema de interés."""
    fecha = fecha_noticia(noticia)
    if not fecha:
        return -100.0
    edad = max(0.0, (ahora - fecha).total_seconds() / 3600)
    if edad > 72:
        return -100.0

    puntos = max(0.0, 8.0 - edad * 0.22)
    fuentes = noticia.get("fuentes") or []
    nombres = {
        str(f.get("nombre", "")).strip().lower()
        for f in fuentes if f.get("nombre")
    }
    puntos += min(6, max(0, len(nombres) - 1) * 3)

    categoria = str(noticia.get("categoria", ""))
    if categoria == "Tendencias":
        puntos += 3.0
    elif categoria in ("Cali", "Valle del Cauca", "Colombia"):
        puntos += 1.5

    titulo = str(noticia.get("titulo", "")).lower()
    resumen = str(noticia.get("resumen", "")).lower()
    tema = titulo + " " + resumen
    terminos_interes = (
        "elecciones", "salario mínimo", "gasolina", "inflación",
        "gaza", "israel", "iran", "trump", "clima", "lluvia",
        "seguridad", "cali", "colombia", "selección", "fútbol",
        "tecnología", "viral", "tendencia", "alerta"
    )
    puntos += min(3.0, sum(1.0 for termino in terminos_interes if termino in tema))
    return round(puntos, 2)


def seleccionar_noticias(noticias, estado, ahora, cantidad):
    ids_publicados = {
        str(r.get("noticia_id"))
        for r in estado.get("publicaciones", [])
        if r.get("buffer_status") == "sent"
    }

    candidatas = []
    for noticia in noticias:
        noticia_id = str(noticia.get("id", "")).strip()
        if not noticia_id or noticia_id in ids_publicados:
            continue
        apto, motivo = articulo_apto(noticia)
        if not apto:
            continue
        puntuacion = puntuacion_editorial(noticia, ahora)
        if puntuacion < 0:
            continue
        candidatas.append((puntuacion, noticia))

    candidatas.sort(
        key=lambda item: (
            item[0],
            fecha_noticia(item[1]) or datetime.min.replace(tzinfo=TZ_COLOMBIA)
        ),
        reverse=True
    )

    elegidas = []
    for puntuacion, noticia in candidatas:
        repetida = False
        for anterior in elegidas:
            if similitud_titulos(
                noticia.get("titulo", ""),
                anterior[1].get("titulo", "")
            ) >= 0.16:
                repetida = True
                print(
                    "Se evita duplicar tema en la cola:",
                    noticia.get("titulo", "")
                )
                break
        if not repetida:
            elegidas.append((puntuacion, noticia))
        if len(elegidas) >= cantidad:
            break
    return elegidas


def proximas_franjas(ahora, cantidad):
    horas = (9, 14, 17, 23)
    franjas = []
    for desplazamiento in range(0, 4):
        dia = ahora.date() + timedelta(days=desplazamiento)
        for hora in horas:
            instante = datetime(
                dia.year, dia.month, dia.day, hora, 0,
                tzinfo=TZ_COLOMBIA
            )
            if instante > ahora + timedelta(minutes=2):
                franjas.append(instante)
            if len(franjas) >= cantidad:
                return franjas
    return franjas


def editar_o_crear_en_franja(noticia, puntuacion, franja, registro, post):
    due_at = franja.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    noticia_id = str(noticia["id"])
    titulo_anterior = str(registro.get("titulo", "")) if registro else ""

    if registro and post:
        post_id = str(post["id"])
        if (
            str(registro.get("noticia_id")) != noticia_id
            or str(post.get("dueAt", "")) != due_at
            or not titulo_anterior
        ):
            resultado = editar_publicacion(post_id, noticia, due_at)
            print("PUBLICACIÓN PENDIENTE ACTUALIZADA EN BUFFER.")
        else:
            resultado = post

        historial = list(registro.get("reemplazos", []))
        if registro.get("noticia_id") and registro.get("noticia_id") != noticia_id:
            historial.append({
                "noticia_id": registro.get("noticia_id"),
                "titulo": registro.get("titulo", ""),
                "reemplazada_en": fecha_local().isoformat()
            })
        registro.update({
            "noticia_id": noticia_id,
            "titulo": noticia.get("titulo", ""),
            "score_editorial": puntuacion,
            "buffer_due_at": resultado.get("dueAt") or due_at,
            "buffer_status": resultado.get("status") or "scheduled",
            "buffer_channel_id": resultado.get("channelId") or CHANNEL_ID,
            "fecha_actualizacion": fecha_local().isoformat(),
            "reemplazos": historial[-20:]
        })
        return registro

    resultado = crear_publicacion(noticia, due_at)
    nuevo = {
        "noticia_id": noticia_id,
        "buffer_post_id": resultado.get("id", ""),
        "titulo": noticia.get("titulo", ""),
        "score_editorial": puntuacion,
        "buffer_due_at": resultado.get("dueAt") or due_at,
        "buffer_status": resultado.get("status") or "scheduled",
        "buffer_channel_id": resultado.get("channelId") or CHANNEL_ID,
        "fecha": fecha_local().isoformat(),
        "reemplazos": []
    }
    print("PUBLICACIÓN AÑADIDA A BUFFER EN HORA FIJA.")
    print("Noticia:", nuevo["titulo"])
    print("Post ID:", nuevo["buffer_post_id"])
    return nuevo


def ejecutar():
    if not TOKEN:
        raise SystemExit("Falta el secreto BUFFER_ACCESS_TOKEN.")

    cache = leer_json(CACHE, {"noticias": []})
    noticias = cache.get("noticias", []) if isinstance(cache, dict) else []
    estado = leer_json(STATE, {"publicaciones": [], "fecha": ""})
    if not isinstance(estado, dict):
        estado = {"publicaciones": [], "fecha": ""}

    ahora = fecha_local()
    hoy = ahora.strftime("%Y-%m-%d")
    estado["fecha"] = hoy
    registros = estado.get("publicaciones", [])
    if not isinstance(registros, list):
        registros = []

    posts_buffer = obtener_posts_programados()
    posts_por_id = {str(p["id"]): p for p in posts_buffer}
    registros_por_post = {
        str(r.get("buffer_post_id")): r
        for r in registros
        if r.get("buffer_post_id")
    }

    pendientes = []
    for registro in registros:
        post_id = str(registro.get("buffer_post_id", ""))
        post = posts_por_id.get(post_id)
        if post:
            registro["buffer_status"] = post.get("status", "scheduled")
            registro["buffer_due_at"] = post.get("dueAt") or registro.get("buffer_due_at")
            registro["buffer_channel_id"] = post.get("channelId") or CHANNEL_ID
            if post.get("status") == "scheduled":
                pendientes.append((registro, post))
        else:
            due = registro.get("buffer_due_at")
            try:
                due_dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                due_local = due_dt.astimezone(TZ_COLOMBIA)
            except (TypeError, ValueError):
                due_local = None

            if registro.get("buffer_status") == "scheduled" and due_local and due_local <= ahora:
                registro["buffer_status"] = "sent"
                registro["sent_at_estimada"] = due_local.isoformat()
                print("Post dejó la cola al llegar su hora; se marca como enviado:", post_id)
            elif registro.get("buffer_status") == "scheduled":
                registro["buffer_status"] = "not_found_in_buffer"

    franjas = proximas_franjas(ahora, 4)
    if not franjas:
        print("No hay franjas futuras disponibles.")
        estado["publicaciones"] = registros[-500:]
        guardar_json(STATE, estado)
        return

    elegidas = seleccionar_noticias(noticias, estado, ahora, len(franjas))
    print("Franjas objetivo:", ", ".join(x.strftime("%d/%m %H:%M") for x in franjas))
    print("Noticias aptas para la cola:", len(elegidas))

    # Solo se reutilizan posts creados por este automatismo y que Buffer
    # confirma que siguen programados. Nunca se modifican posts ajenos.
    libres = list(pendientes)
    asignadas = []
    nuevos_registros = []

    for indice, (puntuacion, noticia) in enumerate(elegidas):
        noticia_id = str(noticia["id"])
        preferido = next(
            (
                par for par in libres
                if str(par[0].get("noticia_id")) == noticia_id
            ),
            None
        )
        if preferido is None and libres:
            # Reaprovecha el post pendiente más tardío para sustituir
            # un contenido que ha perdido prioridad.
            preferido = max(
                libres,
                key=lambda par: str(par[1].get("dueAt", ""))
            )

        if preferido:
            libres.remove(preferido)
            registro, post = preferido
            actualizado = editar_o_crear_en_franja(
                noticia, puntuacion, franjas[indice], registro, post
            )
        else:
            actualizado = editar_o_crear_en_franja(
                noticia, puntuacion, franjas[indice], None, None
            )
        nuevos_registros.append(actualizado)
        asignadas.append(noticia_id)
        print(
            f"Prioridad editorial {puntuacion}: "
            f"{noticia.get('titulo', '')} → "
            f"{franjas[indice].strftime('%d/%m/%Y %I:%M %p')}"
        )

    # Si hay posts propios sobrantes por cambios de configuración,
    # se eliminan solo después de tener asignadas las franjas objetivo.
    for registro, post in libres:
        try:
            eliminar_publicacion(str(post["id"]))
            registro["buffer_status"] = "replaced"
            registro["replaced_at"] = ahora.isoformat()
            print("Post pendiente sobrante retirado de Buffer:", post["id"])
        except Exception as error:
            print("No se pudo retirar un post sobrante:", str(error))
            nuevos_registros.append(registro)

    ids_mantenidos = {
        str(r.get("buffer_post_id"))
        for r in nuevos_registros
        if r.get("buffer_post_id")
    }
    historicos = [
        r for r in registros
        if str(r.get("buffer_post_id")) not in ids_mantenidos
    ]
    estado["publicaciones"] = (historicos + nuevos_registros)[-500:]
    estado["publicaciones_hoy"] = sum(
        1 for r in nuevos_registros
        if r.get("buffer_status") == "scheduled"
        and str(r.get("buffer_due_at", "")).startswith(hoy)
    )
    estado["fecha"] = hoy

    confirmados = obtener_posts_programados()
    confirmados_por_id = {str(p["id"]): p for p in confirmados}
    cantidad_confirmada = 0
    for registro in nuevos_registros:
        post = confirmados_por_id.get(str(registro.get("buffer_post_id", "")))
        if post:
            registro["buffer_due_at"] = post.get("dueAt")
            registro["buffer_status"] = post.get("status")
            registro["buffer_channel_id"] = post.get("channelId")
            cantidad_confirmada += 1

    guardar_json(STATE, estado)
    print("--------------------------------")
    print("Posts propios confirmados en Buffer:", cantidad_confirmada)
    print("Posts programados:", len(nuevos_registros))
    print("Límite de publicaciones por día:", MAX_PUBLICACIONES_POR_DIA)
    print("La cola se revisará de nuevo en el siguiente ciclo.")
    print("--------------------------------")


if __name__ == "__main__":
    ejecutar()
