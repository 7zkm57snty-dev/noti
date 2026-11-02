import os
import requests

TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN")
CHANNEL_ID = "6ae80f3ce29c69a171328e5d"

if not TOKEN:
    raise SystemExit("ERROR: falta el secreto BUFFER_ACCESS_TOKEN")

texto = (
    "🧪 PRUEBA TÉCNICA | CEV NOTICIAS\n\n"
    "Esta es una publicación de prueba creada automáticamente desde GitHub "
    "para verificar la integración con Buffer. No es una noticia real.\n\n"
    "#CEVNoticias #PruebaTecnica"
)

query = """
mutation CreateDraftPost {
  createPost(input: {
    text: %s,
    channelId: "%s",
    schedulingType: automatic,
    mode: addToQueue,
    saveToDraft: true
  }) {
    ... on PostActionSuccess {
      post {
        id
        text
      }
    }
    ... on MutationError {
      message
    }
  }
}
""" % (__import__("json").dumps(texto, ensure_ascii=False), CHANNEL_ID)

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
    print("BORRADOR CREADO CORRECTAMENTE")
    print("POST_ID=" + str(post.get("id", "")))
    print("Estado: borrador en Buffer; no se ha programado ni publicado.")
elif result.get("message"):
    raise SystemExit("Buffer rechazó la solicitud: " + result["message"])
else:
    raise SystemExit("Respuesta inesperada de Buffer: " + str(data))
