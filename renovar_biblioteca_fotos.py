#!/usr/bin/env python3
"""Renueva una biblioteca de fotografías reales para los respaldos de CEV NOTICIAS."""
import json, re, time
from pathlib import Path
from urllib.parse import unquote
import requests

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets" / "biblioteca-fotos"
MANIFEST = BASE / "biblioteca_fotos.json"
HEADERS = {"User-Agent": "CEVNoticias/1.0 (https://cevnoticias.com; archivo editorial)", "Accept": "application/json,image/*"}
CATEGORIAS = {
    "Cali": [
        "Santiago de Cali Colombia city streets",
        "Cali Colombia aerial city skyline",
        "Cali Colombia public transport MIO",
        "Cali Colombia urban public spaces",
        "Cali Colombia community events"
    ],
    "Valle del Cauca": [
        "Valle del Cauca Colombia landscape",
        "Valle del Cauca coffee region",
        "Valle del Cauca Colombia sugar cane agriculture",
        "Palmira Buga Buenaventura Valle del Cauca"
    ],
    "Colombia": [
        "Colombia Bogota city landmark",
        "Colombia landscape Andes",
        "Colombia public infrastructure city",
        "Colombia community public events"
    ],
    "Internacional": [
        "world city skyline international",
        "global city aerial view",
        "international diplomacy conference",
        "world public events crowd"
    ],
    "Deportes": [
        "football soccer match action players stadium",
        "athletics track running race marathon runners",
        "cycling road race peloton cyclists",
        "basketball game court athletes",
        "swimming competition pool athletes",
        "volleyball tennis sports competition",
        "football stadium crowd goal goalkeeper",
        "Colombia sports national team competition"
    ],
    "Tecnología": [
        "technology data center server racks",
        "computer circuit board electronics",
        "robotics industrial automation",
        "artificial intelligence computer technology"
    ],
    "Economía": [
        "business commerce market stock exchange",
        "industrial factory production",
        "retail market small business commerce",
        "Colombia logistics port cargo containers"
    ],
    "Tendencias": [
        "urban culture lifestyle fashion",
        "modern culture exhibition",
        "music concert cultural festival",
        "urban art public exhibition"
    ],
    "Humor y opinión": [
        "newspaper press editorial newsroom",
        "journalism newspaper printing",
        "press conference journalist microphones"
    ],
    "Ciencia y espacio": [
        "planetarium astronomy projection stars",
        "astronomy telescope observatory night sky",
        "space exploration rocket launch spacecraft",
        "science museum planetarium exhibition"
    ],
    "Emergencias": [
        "firefighters emergency rescue response",
        "earthquake rescue emergency services",
        "flood emergency response rescue workers",
        "civil defense disaster response"
    ],
    "Movilidad": [
        "urban traffic street transportation",
        "road construction traffic infrastructure",
        "public transport bus city",
        "cycling urban mobility pedestrian"
    ],
    "Salud pública": [
        "hospital doctors healthcare",
        "public health medical team",
        "vaccination healthcare clinic",
        "medical research laboratory"
    ],
    "General": [
        "news editorial photography press camera",
        "journalism city street photography",
        "press conference media briefing",
        "community public event reportage"
    ]
}
MAX_POR_CATEGORIA = 16
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}

def limpia(valor):
    return re.sub(r"<[^>]+>", "", str(valor or "")).strip()

def consulta_commons(consulta):
    params = {"action":"query","generator":"search","gsrsearch":f"{consulta} filetype:bitmap",
              "gsrnamespace":6,"gsrlimit":30,"prop":"imageinfo","iiprop":"url|extmetadata",
              "iiurlwidth":1400,"format":"json"}
    r=requests.get("https://commons.wikimedia.org/w/api.php",params=params,headers=HEADERS,timeout=25)
    r.raise_for_status()
    return list(r.json().get("query",{}).get("pages",{}).values())

def renovar():
    ASSETS.mkdir(parents=True,exist_ok=True)
    try: anterior=json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError,ValueError): anterior={"version":1,"categorias":{}}
    nuevo={"version":1,"actualizado":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"categorias":{}}
    for categoria,consultas in CATEGORIAS.items():
        elegidas=[]; vistos=set()
        for consulta in consultas:
            try: paginas=consulta_commons(consulta)
            except requests.RequestException as e:
                print(f"Commons no disponible ({categoria}): {e}"); continue
            for pagina in paginas:
                if len(elegidas)>=MAX_POR_CATEGORIA: break
                info=(pagina.get("imageinfo") or [{}])[0]
                meta=info.get("extmetadata",{})
                licencia=limpia(meta.get("LicenseShortName",{}).get("value",""))
                clave=re.sub(r"[^a-z0-9-]","",licencia.lower())
                if not any(x in clave for x in ("ccby","cc-by","cc0","publicdomain","public-domain","pdm")) or "nc" in clave or "nd" in clave:
                    continue
                url=info.get("thumburl") or info.get("url","")
                pagina_url=info.get("descriptionurl","")
                if not url.startswith("https://") or not pagina_url or pagina_url in vistos: continue
                vistos.add(pagina_url)
                try:
                    resp=requests.get(url,headers=HEADERS,timeout=30); resp.raise_for_status()
                    tipo=resp.headers.get("Content-Type","").split(";")[0].lower()
                    ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}.get(tipo)
                    if not ext or len(resp.content)<5000 or len(resp.content)>12*1024*1024: continue
                    nombre=re.sub(r"[^a-z0-9]+","-",categoria.lower()).strip("-")
                    nombre=f"{nombre}-{len(elegidas)+1}{ext}"
                    (ASSETS/nombre).write_bytes(resp.content)
                    elegidas.append({"archivo":f"assets/biblioteca-fotos/{nombre}",
                        "fuente":"Wikimedia Commons","autor":limpia(meta.get("Artist",{}).get("value","Autor no identificado")),
                        "pagina":pagina_url,"licencia":licencia,
                        "licencia_url":limpia(meta.get("LicenseUrl",{}).get("value",""))})
                except requests.RequestException as e: print("No se pudo descargar foto:",e)
            if len(elegidas)>=MAX_POR_CATEGORIA: break
        if len(elegidas)<3 and anterior.get("categorias",{}).get(categoria):
            # Conserva la biblioteca anterior si la fuente falla temporalmente.
            elegidas.extend(anterior["categorias"][categoria])
        nuevo["categorias"][categoria]=elegidas[:MAX_POR_CATEGORIA]
        print(f"{categoria}: {len(nuevo['categorias'][categoria])} fotografías disponibles")
    MANIFEST.write_text(json.dumps(nuevo,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    total=sum(len(x) for x in nuevo["categorias"].values())
    if total==0: raise SystemExit("No se pudo construir la biblioteca de fotografías")
    print(f"Biblioteca lista: {total} fotografías.")

if __name__=="__main__": renovar()
