#!/usr/bin/env python3
"""Verifica que el dominio público sirve el contenido del último despliegue."""
import html.parser
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = os.environ.get("SITE_URL", "https://cevnoticias.com/").strip()
SHA = os.environ.get("BUILD_SHA", "local").strip()
TRIES = int(os.environ.get("VERIFY_ATTEMPTS", "55"))
PAUSE = int(os.environ.get("VERIFY_RETRY_SECONDS", "10"))
CATEGORIES = {"Cali","Valle del Cauca","Colombia","Internacional","Deportes","Tecnología","Economía","Tendencias","Humor y opinión"}

class VisiblePage(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.images = [], []
    def handle_starttag(self, tag, attrs):
        if tag in {"article","div","h1","h2","h3","li","main","p","section"}:
            self.parts.append(" ")
        if tag == "img":
            self.images.append(dict(attrs))
    def handle_endtag(self, tag):
        if tag in {"article","div","h1","h2","h3","li","main","p","section"}:
            self.parts.append(" ")
    def handle_data(self, data):
        self.parts.append(data)
    @property
    def text(self):
        return " ".join("".join(self.parts).split())

def norm(value):
    return " ".join(str(value or "").replace("\u00a0"," ").split()).casefold()

def fetch(path, attempt):
    url = urllib.parse.urljoin(SITE.rstrip("/")+"/", path.lstrip("/"))
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query.append(("_cev_verify", f"{SHA[:12]}-{attempt}-{time.time_ns()}"))
    url = urllib.parse.urlunsplit((parts.scheme,parts.netloc,parts.path,urllib.parse.urlencode(query),parts.fragment))
    req = urllib.request.Request(url, headers={
        "User-Agent":"CEV-NOTICIAS-Publication-Verification/1.0",
        "Accept":"text/html,image/*,*/*;q=0.8",
        "Cache-Control":"no-cache, no-store, max-age=0",
        "Pragma":"no-cache", "Expires":"0"
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data=response.read(20*1024*1024+1)
            if len(data)>20*1024*1024: raise RuntimeError("Respuesta superior a 20 MB")
            return response.status, data, response.headers.get_content_type().lower()
    except urllib.error.HTTPError as error:
        return error.code, error.read(4096), error.headers.get_content_type().lower()

def parse(data):
    page=VisiblePage()
    page.feed(data.decode("utf-8",errors="replace"))
    page.close()
    return page

def sources_ok(article):
    for source in article.get("fuentes",[]) or []:
        if not isinstance(source,dict): continue
        parts=urllib.parse.urlsplit(str(source.get("url","")).strip())
        if parts.scheme=="https" and parts.hostname and str(source.get("nombre","")).strip() and str(source.get("titulo","")).strip():
            return True
    return False

def load_json(raw):
    try: return json.loads(raw)
    except Exception: return {}

def main():
    current=load_json(Path("cache.json").read_text(encoding="utf-8"))
    previous={}
    old=subprocess.run(["git","show","HEAD^:cache.json"],capture_output=True,text=True,check=False)
    if old.returncode==0: previous=load_json(old.stdout)
    old_map={str(n.get("id")):n for n in previous.get("noticias",[]) or [] if n.get("id")}
    new_map={str(n.get("id")):n for n in current.get("noticias",[]) or [] if n.get("id")}
    changed={k for k,v in new_map.items() if old_map.get(k)!=v}
    removed=set(old_map)-set(new_map)
    articles=[]
    seen=set()
    for n in current.get("noticias",[]) or []:
        title=str(n.get("titulo","")).strip()
        body=str(n.get("contenido","")).strip()
        category=n.get("categoria","")
        ident=str(n.get("id","")).strip()
        if not title or len(body)<250 or category not in CATEGORIES or not ident or not sources_ok(n): continue
        if ident in seen: continue
        seen.add(ident); articles.append(n)
    if not articles: raise SystemExit("No se encontraron artículos publicables para verificar.")
    selected=[n for n in articles if not changed or str(n["id"]) in changed] or articles
    print(f"Dominio: {SITE} · commit: {SHA}")
    print(f"Noticias a comprobar: {len(selected)}")
    latest=[]
    for attempt in range(1,TRIES+1):
        try:
            status,home_raw,ctype=fetch("/",attempt)
            if status!=200 or "html" not in ctype: raise RuntimeError(f"Portada HTTP {status} ({ctype})")
            home=norm(parse(home_raw).text)
            errors=[]
            for article in selected:
                ident=str(article["id"])
                status,raw,ctype=fetch(f"/notas/{ident}.html",attempt)
                if status!=200 or "html" not in ctype:
                    errors.append(f"{ident}: página individual HTTP {status}")
                    continue
                page=parse(raw); text=norm(page.text)
                expected=[
                    ("titular",article.get("titulo","")),
                    ("resumen",article.get("resumen","")),
                    ("contenido completo",article.get("contenido","")),
                    ("categoría",article.get("categoria",""))
                ]
                for label,value in expected:
                    if norm(value) not in text: errors.append(f"{ident}: {label} no coincide con cache.json")
                for label,value in expected[:2]+expected[3:]:
                    if norm(value) not in home: errors.append(f"{ident}: la portada no refleja {label}")
                old_image=str(old_map.get(ident,{}).get("imagen","")).strip()
                new_image=str(article.get("imagen","")).strip()
                if ident in changed and old_image!=new_image:
                    photo=next((im for im in page.images if "foto" in str(im.get("class","")).split()),None)
                    if new_image and not photo:
                        errors.append(f"{ident}: la nueva fotografía no aparece en la noticia")
                    elif not new_image and photo:
                        errors.append(f"{ident}: la fotografía retirada sigue apareciendo")
                    elif new_image and photo:
                        photo_path=str(photo.get("src",""))
                        if not photo_path.startswith("/imagenes/"):
                            errors.append(f"{ident}: la fotografía no usa el archivo local")
                        else:
                            ps,pdata,ptype=fetch(photo_path,attempt)
                            if ps!=200 or not ptype.startswith("image/") or len(pdata)<2048:
                                errors.append(f"{ident}: el archivo de fotografía no se sirve correctamente")
            for ident in removed:
                rs,_,_=fetch(f"/notas/{ident}.html",attempt)
                if rs!=404: errors.append(f"{ident}: noticia retirada aún responde HTTP {rs}")
            if not errors:
                print(f"VERIFICACIÓN CORRECTA: portada y {len(selected)} noticias coinciden con cache.json.")
                return
            latest=errors
            print(f"Intento {attempt}/{TRIES}: el dominio aún no refleja todos los cambios.")
            for error in errors[:15]: print(" - "+error)
        except Exception as error:
            latest=[str(error)]
            print(f"Intento {attempt}/{TRIES}: {error}")
        if attempt<TRIES: time.sleep(PAUSE)
    detail="\n".join(" - "+e for e in latest[:20])
    raise SystemExit("GitHub Pages terminó el despliegue, pero cevnoticias.com no confirmó el contenido nuevo. El panel no marcará la actualización como lista.\n"+detail)

if __name__=="__main__":
    main()
