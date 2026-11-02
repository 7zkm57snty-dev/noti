import os
import json
import requests

TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN")
CHANNEL_ID = "6ae80f3ce29c69a171328e5d"

if not TOKEN:
    raise SystemExit("ERROR: falta el secreto BUFFER_ACCESS_TOKEN")

# Fotografía real del centro de Cali, publicada en Wikimedia Commons.
# Autor: Johannes Bud. Licencia: CC BY-SA 4.0.
IMAGE_URL = "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/da/Cali_downtown-_skyline.jpg/1280px-Cali_downtown-_skyline.jpg"

texto = (
    "🧪 PRUEBA TÉCNICA | CEV NOTICIAS\n\n"
    "Prueba de integración con imagen real de Cali. Esta publicación no corresponde "
    "a una noticia ni a un hecho de actualidad.\n\n"
    "Fotografía: Johannes Bud / Wikimedia Commons. "
    "Licencia: CC BY-SA 4.0. "
    "https://creativecommons.org/licenses/by-sa/4.0/\n"
    "Imagen original: https://commons.wikimedia.org/wiki/File:Cali_downtown-_skyline.jpg\n\n"
    "#CEVNoticias #Cali"
)

query = """
mutation CreateDraftPost {
  createPost(input: {
    text: %s,
    channelId: "%s",
    schedulingType: automatic,
    mode: addToQueue,
    saveToDraft: true,
    assets: [
      {
        image: {
          url: "%s"
        }
      }
    ],
    metadata: {
      instagram: {
        type: post,
        shouldShareToFeed: true
      }
    }
  }) {
    ... on PostActionSuccess {
      post {
        id
        text
        assets {
          id
          mimeType
          source
        }
      }
    }
    ... on MutationError {
      message
    }
  }
}
""" % (json.dumps(texto, ensure_ascii=False), CHANNEL_ID, IMAGE_URL)

response = requests.post(
    "https://api.buffer.com",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    },
    json={"query": query},
    timeout=30,
)
response.raise_for_status()
data = response.json()

if data.get("errors"):
    raise SystemExit("ERROR GraphQL: " + str(data["errors"]))

result = data.get("data", {}).get("createPost", {})
if result.get("post"):
    post = result["post"]
    print("BORRADOR CON IMAGEN CREADO CORRECTAMENTE")
    print("POST_ID=" + str(post.get("id", "")))
    print("Estado: borrador en Buffer; no se ha programado ni publicado.")
    print("Imagen: fotografía real de Cali, Johannes Bud / Wikimedia Commons (CC BY-SA 4.0).")
elif result.get("message"):
    raise SystemExit("Buffer rechazó la solicitud: " + result["message"])
else:
    raise SystemExit("Respuesta inesperada de Buffer: " + str(data))
