"""Ventanas de cobertura para las dos ediciones semanales de mini-noticias CEV NOTICIAS."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA_COLOMBIA = ZoneInfo("America/Bogota")
HORA_EDICION = time(6, 0)


def obtener_periodo_breves(ahora=None):
    """Devuelve la ventana fija de la edición del lunes o viernes, desde las 6:00 a. m."""
    if ahora is None:
        ahora = datetime.now(ZONA_COLOMBIA)
    elif ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=ZONA_COLOMBIA)
    else:
        ahora = ahora.astimezone(ZONA_COLOMBIA)

    if ahora.timetz().replace(tzinfo=None) < HORA_EDICION:
        return None

    if ahora.weekday() == 0:
        dia = "lunes"
        fecha_inicio = ahora.date() - timedelta(days=3)
    elif ahora.weekday() == 4:
        dia = "viernes"
        fecha_inicio = ahora.date() - timedelta(days=4)
    else:
        return None

    inicio = datetime.combine(fecha_inicio, HORA_EDICION, tzinfo=ZONA_COLOMBIA)
    fin = datetime.combine(ahora.date(), HORA_EDICION, tzinfo=ZONA_COLOMBIA)
    return {"clave": f"{dia}-{ahora.date().isoformat()}", "dia": dia, "inicio": inicio, "fin": fin}


def grupo_en_periodo_breves(grupo, periodo):
    """Acepta un hecho solo si su fuente más reciente cae dentro de la ventana programada."""
    if not isinstance(periodo, dict):
        return False

    fechas = []
    for fuente in grupo.get("fuentes", []) if isinstance(grupo, dict) else []:
        if not isinstance(fuente, dict):
            continue
        valor = str(fuente.get("fecha", "")).strip()
        if not valor:
            continue
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            fechas.append(fecha.astimezone(ZONA_COLOMBIA))
        except (TypeError, ValueError, OverflowError):
            continue

    if not fechas:
        return False
    fecha_hecho = max(fechas)
    return periodo["inicio"] <= fecha_hecho < periodo["fin"]
