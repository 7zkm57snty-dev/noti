"""Redacta notas breves propias a partir de titulares confirmados por 2 medios o más."""
import hashlib, html, json, os, re, textwrap, time, unicodedata, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

MODELO = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
CLAVE = os.environ.get("GEMINI_API_KEY", "")
MAX_NUEVAS = 6          # notas nuevas por ejecución, para no pasar el límite gratis
DIAS_CACHE = 7
HORAS_PORTADA = 72
# Temas sensibles: no se reescriben, solo se enlaza al medio original
SENSIBLE = re.compile(r"muer|muri|fallec|atropell|ahog|asesin|homicid|cadaver|sin vida|masacre|captur|judicial|fiscal|imput|"
                      r"menor|\bnin[oa]s?\b|abus|violaci|sexual|suicid|desaparec|secuestr|accident|herid|baleado|sicari")
EXTRA_CSS = (".nota{max-width:68ch;margin:28px auto}.nota h1{font:700 clamp(28px,5vw,40px)/1.15 Georgia,serif;margin:14px 0}"
             ".nota svg{width:100%;height:auto;display:block}.nota p{color:var(--fg);font-size:18px}"
             ".aviso{font-size:14px;color:var(--mut);border-top:1px solid var(--line);margin-top:24px;padding-top:12px}"
             ".card svg,.principal svg{width:100%;height:auto;display:block;margin-bottom:8px}")


def _sin(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def esc(t):
    return html.escape(t, quote=True)


def svg(titulo, cat):
    lineas = textwrap.wrap(titulo, 26)[:4]
    t = "".join(f'<tspan x="36" dy="{0 if i == 0 else 46}">{esc(l)}</tspan>' for i, l in enumerate(lineas))
    return (f'<svg viewBox="0 0 640 336" role="img" aria-label="{esc(titulo)}" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="640" height="336" fill="#b3121e"/>'
            f'<text x="36" y="52" fill="#fff" font-family="system-ui,sans-serif" font-size="20" font-weight="600">{esc(cat)}</text>'
            f'<text x="36" y="120" fill="#fff" font-family="Georgia,serif" font-size="38" font-weight="700">{t}</text>'
            '<text x="36" y="312" fill="#fff" font-family="Georgia,serif" font-size="22" font-weight="700">CEV NOTICIAS</text></svg>')


def grupos(notas):
    """Agrupa titulares del mismo hecho. Solo vale si lo cubren 2 medios distintos. El primero es el pionero."""
    usados, salida = set(), []
    orden = sorted(notas, key=lambda n: n["fecha"])
    for a in orden:
        if id(a) in usados:
            continue
        g = [b for b in orden if id(b) not in usados and (b is a or (
            b["fuente"] != a["fuente"] and a["pal"] and b["pal"] and len(a["pal"] & b["pal"]) / len(a["pal"] | b["pal"]) >= 0.5))]
        if len({n["fuente"] for n in g}) >= 2:
            usados.update(id(n) for n in g)
            salida.append(g)
    return salida


def reescribir(g):
    datos = "\n".join(f"- {n['fuente']}: {n['titulo']}. {n['resumen']}".strip() for n in g)
    prompt = ("Eres redactor de CEV NOTICIAS, un medio digital de Cali, Colombia. Con SOLO los hechos de estos titulares y "
              "resúmenes, escribe una nota breve de 50 a 90 palabras. No agregues datos, cifras, nombres ni causas que no "
              "estén en ellos. No copies frases literales. Tono directo y claro, sin adjetivos exagerados. "
              'Responde solo JSON con las claves "titulo" y "texto".\n\n' + datos)
    cuerpo = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent",
                                 data=cuerpo, headers={"Content-Type": "application/json", "x-goog-api-key": CLAVE})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
        titulo, texto = " ".join(j["titulo"].split()), " ".join(j["texto"].split())
    except Exception as e:
        print("FALLO IA:", e)
        return None
    nums = lambda s: set(re.findall(r"\d+", s))
    if not (25 <= len(texto.split()) <= 140 and 10 <= len(titulo) <= 120) or not nums(titulo + texto) <= nums(datos):
        print("RECHAZADA por validación:", titulo)  # evita cifras inventadas
        return None
    return titulo, texto


def pagina_nota(v, css):
    vistas, lis = set(), ""
    for f in v["fuentes"]:
        if f["fuente"] not in vistas:
            vistas.add(f["fuente"])
            lis += f'<li><a href="{esc(f["link"])}" target="_blank" rel="noopener noreferrer">{esc(f["fuente"])}</a></li>'
    pio = v["fuentes"][0]
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(v["titulo"])} | CEV NOTICIAS</title><style>{css}{EXTRA_CSS}</style></head><body>'
            '<header><div class="marca"><a href="../">CEV NOTICIAS</a></div></header>'
            f'<main class="wrap"><article class="nota"><span class="cat">{esc(v["cat"])}</span><h1>{esc(v["titulo"])}</h1>'
            f'{svg(v["titulo"], v["cat"])}<p class="meta">Primicia de <a href="{esc(pio["link"])}" target="_blank" '
            f'rel="noopener noreferrer"><b>{esc(pio["fuente"])}</b></a></p><p>{esc(v["texto"])}</p>'
            f'<p><b>Fuentes</b></p><ul>{lis}</ul>'
            '<p class="aviso">Nota breve redactada con ayuda de inteligencia artificial a partir de los titulares de los '
            'medios citados. Para ver el detalle completo, lee la nota original en la fuente.</p></article></main></body></html>')


def generar(notas, css, ahora):
    """Devuelve (notas propias, ids de las notas que reemplazan)."""
    ruta = Path("cache.json")
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    corte = ahora - timedelta(days=DIAS_CACHE)
    cache = {k: v for k, v in cache.items() if datetime.fromisoformat(v["fecha"]) > corte}
    nuevas, miembros, vigentes = 0, set(), {}
    for g in grupos(notas):
        pio = g[0]
        k = hashlib.sha1(pio["link"].encode()).hexdigest()[:10]
        if k not in cache:
            if (SENSIBLE.search(_sin(" ".join(n["titulo"] + " " + n["resumen"] for n in g)))
                    or not CLAVE or nuevas >= MAX_NUEVAS):
                continue
            if nuevas:
                time.sleep(13)  # el plan gratis limita las peticiones por minuto
            nuevas += 1
            r = reescribir(g)
            if not r:
                continue
            cache[k] = {"titulo": r[0], "texto": r[1], "cat": pio["cat"], "fecha": pio["fecha"].isoformat(),
                        "fuentes": [{"fuente": n["fuente"], "link": n["link"]} for n in g]}
        miembros.update(id(n) for n in g)
        vigentes[k] = g
    if cache:
        Path("site/notas").mkdir(parents=True, exist_ok=True)
        for k, v in cache.items():
            Path(f"site/notas/{k}.html").write_text(pagina_nota(v, css), encoding="utf-8")
        ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    propias = []
    for k, v in cache.items():
        fecha = datetime.fromisoformat(v["fecha"])
        if ahora - fecha > timedelta(hours=HORAS_PORTADA):
            continue
        pionero = v["fuentes"][0]["fuente"]
        otras = {f["fuente"] for f in v["fuentes"]} - {pionero}
        propias.append({"cat": v["cat"], "fuente": "CEV NOTICIAS", "titulo": v["titulo"], "link": f"notas/{k}.html",
                        "fecha": fecha, "resumen": "", "otras": otras, "pal": set(), "propia": True,
                        "pionero": pionero})
    return propias, miembros
