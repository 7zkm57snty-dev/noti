import json
import os
import sys
import requests

ENDPOINT = "https://api.buffer.com"
TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN")

if not TOKEN:
    raise SystemExit("ERROR: falta el secreto BUFFER_ACCESS_TOKEN en GitHub.")

query = """
query CEVNoticiasConnectionCheck {
  account {
    id
    name
    organizations {
      id
      name
    }
  }
}
"""

try:
    response = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        json={"query": query},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
except requests.RequestException as error:
    raise SystemExit(f"ERROR de conexión con Buffer: {error}")

if payload.get("errors"):
    for error in payload["errors"]:
        print("Buffer API:", error.get("message", "Error desconocido"))
    raise SystemExit("No se pudo consultar la cuenta de Buffer.")

account = payload.get("data", {}).get("account")
if not account:
    raise SystemExit("Buffer no devolvió los datos de la cuenta.")

print("Conexión con Buffer: correcta")
print("Cuenta:", account.get("name") or "(sin nombre)")
organizations = account.get("organizations") or []

if not organizations:
    print("No se encontraron organizaciones en esta cuenta.")
    raise SystemExit(0)

for organization in organizations:
    print("\nOrganización:", organization.get("name") or "(sin nombre)")
    print("ORGANIZATION_ID=" + organization["id"])

    channel_query = """
    query CEVNoticiasChannels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) {
        id
        name
        displayName
        service
        externalLink
      }
    }
    """
    try:
        channel_response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "query": channel_query,
                "variables": {"organizationId": organization["id"]},
            },
            timeout=30,
        )
        channel_response.raise_for_status()
        channel_payload = channel_response.json()
    except requests.RequestException as error:
        print("No se pudieron consultar los canales:", error)
        continue

    if channel_payload.get("errors"):
        for error in channel_payload["errors"]:
            print("Error consultando canales:", error.get("message", "desconocido"))
        continue

    channels = channel_payload.get("data", {}).get("channels") or []
    if not channels:
        print("No hay canales conectados en esta organización.")
        continue

    for channel in channels:
        print(
            "CANAL:",
            channel.get("displayName") or channel.get("name") or "(sin nombre)",
            "| servicio:",
            channel.get("service") or "(no informado)",
            "| enlace:",
            channel.get("externalLink") or "(no disponible)",
        )
        print("CHANNEL_ID=" + channel["id"])

print("\nComprobación terminada. No se ha creado ni publicado ningún post.")
