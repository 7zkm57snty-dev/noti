import hashlib, html, json, os, re, textwrap, time, unicodedata, urllib.request
from datetime import timedelta
from pathlib import Path

try:
    import trafilatura
except ImportError:
    trafilatura = None

MODELO = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
CLAVE = os.environ.get("GEMINI_API_KEY", "")
MAX_NUEVAS = 4
DIAS_CACHE = 10
HORAS_PORTADA = 72
SENSIBLE = re.compile(r"muer|muri|fallec|atropell|ahog|asesin|homicid|cadaver|masacre|captur|judicial|fiscal|imput|menor|nin[oa]s?|abus|violaci|sexual|suicid|desaparec|secuestr|accident|herid|balead|sicari|denuncia|corrup")

EXTRA_CSS = ".nota{max-width:760px;margin:30px auto}.nota h1{font:700 clamp(29px,5vw,43px)/1.15 Georgia,serif}.nota svg{width:100%;margin:22px 0}.nota p{font-size:18px;line-height:1.75;color:var(--fg)}.nota .bajada{font-size:20px;color:var(--mut)}.nota .fuentes{margin-top:28px;padding-top:18px;border-top:1px solid var(--line)}"

def _sin(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")

def esc(t):
    return html.escape(str(t or ""), quote=True)

def svg(titulo, cat):
    lineas = textwrap.wrap(titulo, 27)[:4]
    texto = "".join(f'<tspan x="36" dy="{0 if i == 0 else 46}">{esc(x)}</tspan>' for i,x in enumerate(lineas))
    return ('<svg viewBox="0 0 640 336" role="img" xmlns="http://www.w3.org/2000/svg"><rect width="640" height="336" fill="#b3121e"/>'
            f'<text x="36" y="52" fill="#fff" font-family="system-ui" font-size="20">{esc(cat)}</text>'
            f'<text x="36" y="120" fill="#fff" font-family="Georgia" font-size="38" font-weight="700">{texto}</text>'
            '<text x="36" y="312" fill="#fff" font-family="Georgia" font-size="22" font-weight="700">CEV NOTICIAS</text></svg>')

def extraer(url):
    if not trafilatura:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; CEVNoticias/2.0)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            contenido = r.read(2500000)
        texto = trafilatura.extract(contenido, include_comments=False, include_tables=False, favor_precision=True, deduplicate=True)
        return re.sub(r"\s+", " ", texto or "").strip()
    except Exception as e:
        print(f"No se pudo extraer {url}: {e}")
        return ""

def similar(a,b):
    tokens = lambda s: {w for w in re.findall(r"[a-z0-9]+", _sin(s)) if len(w)>3}
    x,y=tokens(a),tokens(b)
    return bool(x and y and len(x&y)/len(x|y)>=0.35)

def grupos(notas):
    salida=[]; usados=set()
    for a in sorted(notas,key=lambda n:n["_fecha"],reverse=True):
        if id(a) in usados: continue
        g=[a]
        for b in notas:
            if id(b) not in usados and b is not a and b["fuente"]!=a["fuente"] and similar(a["titulo"],b["titulo"]):
                g.append(b)
        if len({n["fuente"] for n in g})>=2:
            usados.update(id(n) for n in g); salida.append(g)
    return salida

def gemini(prompt):
    import json
    datos=json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"responseMimeType":"application/json"}}).encode()
    req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent",data=datos,headers={"Content-Type":"application/json","x-goog-api-key":CLAVE})
    with urllib.request.urlopen(req,timeout=90) as r:
        j=json.loads(r.read().decode())
    return json.loads(j["candidates"][0]["content"]["parts"][0]["text"])

def redactar(grupo,textos):
    material="\n\n---\n\n".join(f"MEDIO: {n['fuente']}\nTITULAR: {n['titulo']}\nTEXTO RECUPERADO: {t[:7000]}" for n,t in zip(grupo,textos))
    prompt=("Eres periodista de CEV NOTICIAS, medio digital de Cali, Colombia. Escribe un artículo original de 180 a 350 palabras en español colombiano claro. "
            "Usa solo hechos respaldados por el material. No inventes nombres, cifras, fechas, declaraciones, causas ni consecuencias. No copies frases. "
            "Si hay contradicciones importantes o información insuficiente, devuelve publicar=false. No confundas titulares parecidos con verificación. "
            "Devuelve solo JSON con publicar (boolean), titulo, bajada y texto. El texto debe tener 3 a 5 párrafos.\n\nMATERIAL:\n"+material)
    j=gemini(prompt)
    if not j.get("publicar"): return None
    titulo=" ".join(str(j.get("titulo","")).split()); bajada=" ".join(str(j.get("bajada","")).split()); texto=" ".join(str(j.get("texto","")).split())
    if not 10<=len(titulo)<=130 or not 20<=len(bajada.split())<=55 or not 180<=len(texto.split())<=350: return None
    nums=lambda s:set(re.findall(r"\d+",s))
    if not nums(titulo+" "+bajada+" "+texto).issubset(nums(material)): return None
    return {"titulo":titulo,"bajada":bajada,"texto":texto}

def pagina_nota(v,css):
    fuentes="".join(f'<li><a href="{esc(f["link"])}" target="_blank" rel="noopener noreferrer">{esc(f["fuente"])}</a></li>' for f in v["fuentes"])
    parrafos="".join(f"<p>{esc(p)}</p>" for p in v["parrafos"])
    return ('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(v["titulo"])} | CEV NOTICIAS</title><meta name="description" content="{esc(v["bajada"])}">'
            f'<style>{css}{EXTRA_CSS}</style></head><body><header><div class="marca"><a href="../">CEV NOTICIAS</a></div></header>'
            f'<main class="wrap"><article class="nota"><span class="cat">{esc(v["cat"])}</span><h1>{esc(v["titulo"])}</h1>{svg(v["titulo"],v["cat"])}'
            f'<p class="bajada">{esc(v["bajada"])}</p>'+''.join(f'<p>{esc(p)}</p>' for p in v["parrafos"])+
            f'<div class="fuentes"><b>Fuentes consultadas</b><ul>{fuentes}</ul></div>'
            '<p class="aviso">Artículo original elaborado con asistencia de inteligencia artificial a partir del contenido consultado en las fuentes enlazadas.</p>'
            '</article></main></body></html>')

def generar(notas,css,ahora):
    ruta=Path("cache.json"); cache=json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    corte=ahora-timedelta(days=DIAS_CACHE)
    cache={k:v for k,v in cache.items() if __import__("datetime").datetime.fromisoformat(v["fecha"])>corte}
    reemplazadas=set(); creadas=0
    for g in grupos(notas):
        pionera=g[0]
        if SENSIBLE.search(_sin(" ".join(n["titulo"]+" "+n.get("resumen","") for n in g))):
            print("Se omite un tema sensible para revisión humana."); continue
        clave=hashlib.sha1("|".join(sorted(n["link"] for n in g)).encode()).hexdigest()[:12]
        if clave not in cache:
            if not CLAVE or creadas>=MAX_NUEVAS: continue
            pares=[(n,extraer(n["link"])) for n in g]
            pares=[(n,t) for n,t in pares if len(t)>=450]
            if len({n["fuente"] for n,t in pares})<2:
                print("Se omite: no se obtuvo texto suficiente de dos medios."); continue
            grupo=[n for n,t in pares]; textos=[t for n,t in pares]
            try: resultado=redactar(grupo,textos)
            except Exception as e:
                print("Fallo de Gemini:",e); resultado=None
            if not resultado: continue
            cache[clave]={**resultado,"cat":pionera["cat"],"fecha":pionera["_fecha"].isoformat(),
                          "fuentes":[{"fuente":n["fuente"],"link":n["link"]} for n in grupo]}
            creadas+=1
            if creadas<MAX_NUEVAS: time.sleep(12)
        reemplazadas.update(id(n) for n in g)
    propias=[]
    Path("site/notas").mkdir(parents=True,exist_ok=True)
    from datetime import datetime
    for k,v in cache.items():
        fecha=datetime.fromisoformat(v["fecha"])
        v["parrafos"]=[p.strip() for p in re.split(r"\n+",v["texto"]) if p.strip()]
        Path(f"site/notas/{k}.html").write_text(pagina_nota(v,css),encoding="utf-8")
        if ahora-fecha<=timedelta(hours=HORAS_PORTADA):
            propias.append({"cat":v["cat"],"fuente":"CEV NOTICIAS","titulo":v["titulo"],"link":f"notas/{k}.html",
                            "_fecha":fecha,"resumen":v["bajada"],"propia":True})
    ruta.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding="utf-8")
    return propias,reemplazadas
