#!/usr/bin/env python3
"""Actualiza el radar RSS de CEV NOTICIAS de forma independiente."""
import hashlib, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import feedparser, requests

ROOT=Path(__file__).resolve().parent
FEEDS_PATH=ROOT/"feeds.json"
RADAR_PATH=ROOT/"radar_rss.json"
MAX_ITEMS=60
MAX_AGE_HOURS=72
HEADERS={"User-Agent":"CEVNoticias-Radar/1.0 (+https://cevnoticias.com/)","Accept":"application/rss+xml, application/xml, text/xml"}
CATEGORIES={
"Cali":("cali","mio ","alcaldia de cali","santiago de cali"),
"Valle del Cauca":("valle del cauca","vallecaucano","buenaventura","palmira","tulua","jamundi","yumbo"),
"Deportes":("futbol","fútbol","liga","deportivo","america de cali","américa de cali","deportes","seleccion","selección","mundial","nba","tenis"),
"Tecnología":("tecnologia","tecnología","inteligencia artificial","software","ciberseguridad","apple","google","microsoft","internet"),
"Economía":("economia","economía","dolar","dólar","banco","inflacion","inflación","mercado","empresas","empleo","petroleo","petróleo"),
"Internacional":("estados unidos","ee.uu","eeuu","ucrania","rusia","guerra","venezuela","mundo","internacional","onu","trump","china"),
"Colombia":("colombia","bogota","bogotá","congreso","presidente","gobierno","ministerio","procuraduria","procuraduría"),
"Tendencias":("viral","redes sociales","entretenimiento","famosos","influencer","musica","música","cine","series")}
def clean(v): return re.sub(r"\s+"," ",str(v or "")).strip()
def category(title,source,zone):
 t=clean(title).lower(); s=(clean(source)+" "+clean(zone)).lower()
 for cat in ("Cali","Valle del Cauca","Deportes","Tecnología","Economía","Internacional","Colombia","Tendencias"):
  if any(word in t for word in CATEGORIES[cat]): return cat
 if any(x in s for x in ("cali","q'hubo")): return "Cali"
 if "90 minutos" in s: return "Valle del Cauca"
 if "deportes" in s or "sport" in s: return "Deportes"
 if "econom" in s or "portafolio" in s: return "Economía"
 if "bbc" in s or "dw español" in s or "internacional" in s: return "Internacional"
 return "Colombia"
def entry_date(entry):
 for field in ("published_parsed","updated_parsed"):
  parsed=entry.get(field)
  if parsed:
   try: return datetime(*parsed[:6],tzinfo=timezone.utc)
   except (TypeError,ValueError,OverflowError): pass
 return None
def main():
 sources=json.loads(FEEDS_PATH.read_text(encoding="utf-8")); now=datetime.now(timezone.utc); cutoff=now-timedelta(hours=MAX_AGE_HOURS)
 headlines=[]; statuses=[]; seen_urls=set(); seen_titles=set()
 for source in sources:
  name,url,zone=clean(source.get("nombre")),clean(source.get("url")),clean(source.get("zona"))
  status={"nombre":name or "Fuente RSS","url":url,"estado":"error","titulares":0}
  try:
   parsed_url=urlparse(url)
   if parsed_url.scheme!="https" or not parsed_url.hostname: raise ValueError("La fuente no utiliza HTTPS.")
   response=requests.get(url,headers=HEADERS,timeout=(5,12)); response.raise_for_status()
   parsed=feedparser.parse(response.content)
   if not parsed.entries: raise ValueError("El feed no contiene entradas.")
   for entry in parsed.entries[:35]:
    title=clean(entry.get("title")); link=clean(entry.get("link")); date=entry_date(entry); host=urlparse(link).hostname or ""
    if not title or not link.startswith("https://") or not host: continue
    if date and (date>now+timedelta(hours=3) or date<cutoff): continue
    url_key=link.split("#",1)[0].rstrip("/"); title_key=re.sub(r"[^a-z0-9]","",title.lower())
    if url_key in seen_urls or title_key in seen_titles: continue
    seen_urls.add(url_key); seen_titles.add(title_key)
    headlines.append({"id":hashlib.sha256(url_key.encode()).hexdigest()[:16],"titulo":title[:240],"categoria":category(title,name,zone),"fuente":name or host,"url":link,"fecha":date.isoformat() if date else now.isoformat(),"imagen":""})
    status["titulares"]+=1
   status["estado"]="correcto" if status["titulares"] else "sin_novedades"
  except Exception as exc: status["detalle"]=clean(exc)[:240]
  statuses.append(status)
 headlines.sort(key=lambda x:x["fecha"],reverse=True)
 data={"ultima_actualizacion":now.isoformat(),"titulares_rss":headlines[:MAX_ITEMS],"estado_fuentes":statuses}
 tmp=RADAR_PATH.with_suffix(".json.tmp"); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); tmp.replace(RADAR_PATH)
 successful=sum(x["estado"]=="correcto" for x in statuses)
 print(f"Radar RSS actualizado: {len(data['titulares_rss'])} titulares, {successful}/{len(statuses)} fuentes con novedades.")
 if successful==0: raise SystemExit("Ninguna fuente RSS produjo titulares.")
if __name__=="__main__": main()
