import dashboardHtml from "./dashboard.html";

const OWNER = "7zkm57snty-dev";
const REPO = "noti";
const MAIN = "main";
const ORIGIN = "https://admin.cevnoticias.com";
const CATEGORIES = ["Cali","Valle del Cauca","Colombia","Internacional","Deportes","Tecnología","Economía","Tendencias","Humor y opinión"];
const API = "https://api.github.com";

class AdminError extends Error {
  constructor(status, message, detail) { super(message); this.status=status; this.detail=detail||null; }
}
const json = (data,status=200) => new Response(JSON.stringify(data), {
  status, headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store, private","x-content-type-options":"nosniff"}
});
function decode64(s) {
  const b=atob(String(s||"").replace(/\s/g,"")), a=new Uint8Array(b.length);
  for(let i=0;i<b.length;i++) a[i]=b.charCodeAt(i);
  return new TextDecoder().decode(a);
}
function encode64(s) {
  const a=new TextEncoder().encode(s); let b="";
  for(let i=0;i<a.length;i+=0x8000) b+=String.fromCharCode(...a.subarray(i,i+0x8000));
  return btoa(b);
}
function dateCO() {
  const p={};
  new Intl.DateTimeFormat("en-GB",{timeZone:"America/Bogota",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:true})
    .formatToParts(new Date()).forEach(x=>p[x.type]=x.value);
  return p.day+"/"+p.month+"/"+p.year+" · "+p.hour+":"+p.minute+" "+p.dayPeriod.toUpperCase();
}
function managedBranch(b) { return b==="revision-editorial/noticias-pendientes" || String(b||"").startsWith("revision-admin/") || String(b||"").startsWith("feature/centro-diagnostico-automatico"); }

async function gh(path,env,method="GET",body) {
  if(!env.GITHUB_TOKEN) throw new AdminError(503,"Falta configurar el secreto GITHUB_TOKEN en Cloudflare.");
  const h={"accept":"application/vnd.github+json","authorization":"Bearer "+env.GITHUB_TOKEN,"x-github-api-version":"2022-11-28","user-agent":"CEVNoticias-Admin/1.0"};
  if(body) h["content-type"]="application/json";
  const r=await fetch(API+path,{method,headers:h,body:body?JSON.stringify(body):undefined});
  const raw=await r.text(); let data={};
  try{data=raw?JSON.parse(raw):{}}catch(_){}
  if(!r.ok){
    const status=[409,422].includes(r.status)?409:r.status===404?404:502;
    const message=r.status===401||r.status===403?"GitHub rechazó el token. Revisa sus permisos.":r.status===404?"No se encontró un recurso del repositorio.":r.status===409||r.status===422?"GitHub detectó un conflicto. Actualiza el panel e inténtalo de nuevo.":"No se pudo completar la operación en GitHub.";
    throw new AdminError(status,message,{githubStatus:r.status});
  }
  return data;
}
async function readCache(env) {
  const f=await gh("/repos/"+OWNER+"/"+REPO+"/contents/cache.json?ref="+MAIN,env);
  if(!f.content||f.encoding!=="base64") throw new AdminError(502,"No se pudo leer cache.json.");
  let data;
  try{data=JSON.parse(decode64(f.content))}catch(_){throw new AdminError(502,"cache.json no contiene JSON válido.")}
  if(!data||!Array.isArray(data.noticias)) throw new AdminError(502,"La estructura de cache.json no coincide con CEV NOTICIAS.");
  return {data,sha:f.sha};
}
async function reviews(env) {
  const all=await gh("/repos/"+OWNER+"/"+REPO+"/pulls?state=open&per_page=100&sort=created&direction=desc",env);
  return all.filter(p=>p.base&&p.base.ref===MAIN&&p.head&&managedBranch(p.head.ref)).map(p=>({
    number:p.number,title:p.title,body:p.body||"",url:p.html_url,branch:p.head.ref,createdAt:p.created_at,author:p.user?p.user.login:"GitHub",
    additions:p.additions||0,deletions:p.deletions||0,changedFiles:p.changed_files||0
  }));
}
async function submitChange(env,mutate,title,description) {
  const pending=await reviews(env);
  if(pending.length) throw new AdminError(409,"Ya existe una propuesta editorial pendiente. Resuélvela antes de crear otra.",{pending});
  const ref1=await gh("/repos/"+OWNER+"/"+REPO+"/git/ref/heads/"+MAIN,env);
  const cached=await readCache(env);
  const ref2=await gh("/repos/"+OWNER+"/"+REPO+"/git/ref/heads/"+MAIN,env);
  if(ref1.object.sha!==ref2.object.sha) throw new AdminError(409,"El repositorio cambió durante la operación. Actualiza el panel e inténtalo otra vez.");
  const updated=mutate(cached.data);
  const branch="revision-admin/panel-"+Date.now()+"-"+crypto.randomUUID().slice(0,8);
  await gh("/repos/"+OWNER+"/"+REPO+"/git/refs",env,"POST",{ref:"refs/heads/"+branch,sha:ref1.object.sha});
  try {
    await gh("/repos/"+OWNER+"/"+REPO+"/contents/cache.json",env,"PUT",{
      message:"Panel CEV: "+description,content:encode64(JSON.stringify(updated,null,2)+"\n"),sha:cached.sha,branch
    });
    const pr=await gh("/repos/"+OWNER+"/"+REPO+"/pulls",env,"POST",{
      title,head:branch,base:MAIN,
      body:"Propuesta creada desde el panel privado de CEV NOTICIAS.\n\nNo se publicará hasta que el administrador la revise y la fusione.\n\nComprueba titular, datos, fuentes y atribución fotográfica."
    });
    return {number:pr.number,title:pr.title,url:pr.html_url,branch};
  } catch(e) {
    try{await gh("/repos/"+OWNER+"/"+REPO+"/git/refs/heads/"+branch,env,"DELETE")}catch(_){}
    throw e;
  }
}
function validateArticle(v) {
  v=v||{};
  const title=String(v.titulo||"").trim(), social=String(v.titular_instagram||title).trim();
  const summary=String(v.resumen||"").trim(), content=String(v.contenido||"").trim();
  const category=String(v.categoria||"").trim(), info=String(v.estado_informacion||"confirmada");
  if(title.length<12) throw new AdminError(400,"El titular debe tener al menos 12 caracteres.");
  if(summary.length<40) throw new AdminError(400,"El resumen debe tener al menos 40 caracteres.");
  if(content.split(/\s+/).filter(Boolean).length<250) throw new AdminError(400,"El artículo debe tener al menos 250 palabras.");
  if(!CATEGORIES.includes(category)) throw new AdminError(400,"Selecciona una categoría válida.");
  if(!["confirmada","en_desarrollo"].includes(info)) throw new AdminError(400,"Selecciona un estado de información válido.");
  const sources=[],domains=new Set();
  for(const s of (Array.isArray(v.fuentes)?v.fuentes:[])) {
    if(!s||(!String(s.nombre||"").trim()&&!String(s.url||"").trim())) continue;
    const name=String(s.nombre||"").trim(), headline=String(s.titulo||"").trim(), link=String(s.url||"").trim();
    let u;try{u=new URL(link)}catch(_){throw new AdminError(400,"Una fuente tiene una URL no válida.")}
    if(u.protocol!=="https:"||!name||!headline) throw new AdminError(400,"Cada fuente debe tener nombre, titular original y URL HTTPS.");
    sources.push({nombre:name,titulo:headline,url:link});domains.add(u.hostname.toLowerCase().replace(/^www\./,""));
  }
  if(!sources.length) throw new AdminError(400,"Añade al menos una fuente directa.");
  const sensitive=/\b(accidente|muert\w*|falleci\w*|homicid\w*|asesinat\w*|robo\w*|hurto\w*|captura\w*|detenid\w*|denuncia\w*|acusaci[oó]n\w*|víctim\w*|victim\w*|agresi[oó]n\w*|desaparici[oó]n\w*|abuso\w*|corrupci[oó]n\w*)/i;
  if(sensitive.test(title+" "+summary+" "+content)&&domains.size<2) throw new AdminError(400,"El tema parece sensible. Añade dos fuentes independientes.");
  const image=String(v.imagen||"").trim();let credit={};
  if(image) {
    let u;try{u=new URL(image)}catch(_){throw new AdminError(400,"La dirección de la fotografía no es válida.")}
    if(u.protocol!=="https:") throw new AdminError(400,"La fotografía debe utilizar HTTPS.");
    const c=v.imagen_credito||{},fields=["autor","fuente","pagina","licencia","licencia_url"];
    for(const f of fields) if(!String(c[f]||"").trim()) throw new AdminError(400,"Completa todos los datos de autoría y licencia de la fotografía.");
    try{if(new URL(c.licencia_url).protocol!=="https:")throw 0}catch(_){throw new AdminError(400,"El enlace de la licencia debe ser HTTPS.")}
    credit={autor:String(c.autor).trim(),fuente:String(c.fuente).trim(),pagina:String(c.pagina).trim(),licencia:String(c.licencia).trim(),licencia_url:String(c.licencia_url).trim()};
  }
  return {titulo:title,titular_instagram:social||title,resumen:summary,categoria:category,contenido:content,estado_informacion:info,
    imagen:image,imagen_credito:credit,verificacion:sources.length>1?"Fuentes independientes":"Una sola fuente",fuentes:sources};
}

function runDiagnostics(cache) {
  const findings = [], titles = new Map(), images = new Map();
  const add = (severity, code, message, id) => findings.push({severity,code,message,articleId:id || null});
  const articles = Array.isArray(cache.noticias) ? cache.noticias : [];
  for (const n of articles) {
    const id = String(n.id || ""), title = String(n.titulo || "").trim();
    const key = title.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g," ").trim();
    if (!title) add("critical","missing_title","Noticia sin titular",id);
    if (key && titles.has(key)) add("warning","duplicate_title","Titular idéntico al registro "+titles.get(key),id);
    else if (key) titles.set(key,id);
    const image = String(n.imagen || "").trim();
    if (!image) add("warning","missing_image","Falta imagen periodística principal; no se sustituye por una portada con texto.",id);
    else {
      try { if (new URL(image).protocol !== "https:") add("critical","image_not_https","La imagen no usa HTTPS.",id); }
      catch (_) { add("critical","invalid_image","URL de imagen no válida.",id); }
      if (images.has(image)) add("warning","duplicate_image","La imagen se repite en otra noticia.",id);
      else images.set(image,id);
    }
    const sources = Array.isArray(n.fuentes) ? n.fuentes : [];
    if (!sources.length) add("critical","missing_sources","Noticia sin fuentes registradas.",id);
    if (sources.length === 1) add("warning","single_source","Noticia con una sola fuente; requiere corroboración.",id);
    for (const source of sources) {
      try { if (new URL(source.url).protocol !== "https:") add("critical","invalid_source","Fuente sin HTTPS.",id); }
      catch (_) { add("critical","invalid_source","URL de fuente no válida.",id); }
    }
    if (String(n.resumen || "").trim().length < 40) add("warning","short_summary","Resumen inferior a 40 caracteres.",id);
    if (String(n.contenido || "").trim().split(/\s+/).filter(Boolean).length < 250) add("warning","short_content","Contenido inferior a 250 palabras.",id);
  }
  return {scannedAt:new Date().toISOString(),articles:articles.length,rssCount:Array.isArray(cache.titulares_rss)?cache.titulares_rss.length:0,findings,counts:{critical:findings.filter(x=>x.severity==="critical").length,warning:findings.filter(x=>x.severity==="warning").length}};
}
function normalizeSafeFields(cache) {
  let changed = 0;
  for (const n of (cache.noticias || [])) {
    for (const key of ["titulo","titular_instagram","resumen","contenido","categoria"]) {
      if (typeof n[key] === "string") {
        const value = n[key].replace(/\r\n/g,"\n").trim().replace(/[ \t]+/g," ");
        if (value !== n[key]) { n[key] = value; changed++; }
      }
    }
  }
  return changed;
}

async function dashboard(env,identity) {
  if(!env.GITHUB_TOKEN) return {configured:false,user:identity.email||identity.name||"Administrador",news:[],reviews:[]};
  const r=await Promise.all([readCache(env),reviews(env)]);
  return {configured:true,user:identity.email||identity.name||"Administrador",news:r[0].data.noticias,reviews:r[1],
    rssCount:Array.isArray(r[0].data.titulares_rss)?r[0].data.titulares_rss.length:0,latestUpdate:r[0].data.ultima_actualizacion||null};
}
async function api(request,env,identity) {
  const url=new URL(request.url),path=url.pathname,method=request.method.toUpperCase();
  if(method==="GET"&&path==="/api/dashboard") return json(await dashboard(env,identity));
  if(method==="GET"&&path==="/api/diagnostics") { const r=await readCache(env); return json(runDiagnostics(r.data)); }
  if(method==="POST"&&path==="/api/diagnostics/repair") { const r=await readCache(env); const count=normalizeSafeFields(r.data); if(!count)return json({ok:true,changed:0,message:"No hay normalizaciones pendientes."}); const pr=await submitChange(env,cache=>{normalizeSafeFields(cache);return cache;},"CEV NOTICIAS | Normalización técnica segura","normalización técnica segura"); return json({ok:true,changed:count,pr,message:"Propuesta de reparación creada para revisión."}); }
  if(method==="GET"&&path==="/api/health") {
    if(!env.GITHUB_TOKEN)return json({ok:false,message:"Falta configurar GITHUB_TOKEN."},503);
    await gh("/repos/"+OWNER+"/"+REPO,env);return json({ok:true,repository:OWNER+"/"+REPO});
  }
  if(!["POST","PATCH","DELETE"].includes(method)) return json({error:"Ruta no encontrada."},404);
  if(request.headers.get("origin")!==ORIGIN) return json({error:"Origen no autorizado."},403);
  let body={};
  if(method!=="DELETE"){
    if(Number(request.headers.get("content-length")||0)>900000)throw new AdminError(413,"El contenido supera el tamaño permitido.");
    try{body=await request.json()}catch(_){throw new AdminError(400,"El cuerpo de la solicitud no contiene JSON válido.")}
  }
  if(method==="POST"&&path==="/api/news"){
    const fields=validateArticle(body);
    const pr=await submitChange(env,cache=>{
      const id=crypto.randomUUID().replace(/-/g,"").slice(0,16);
      cache.noticias.unshift(Object.assign({id,fecha:dateCO(),imagen_busqueda_intentada:false,imagen_instagram:"",imagen_instagram_tipo:"",descripcion_instagram:""},fields));
      return cache;
    },"CEV NOTICIAS | Nueva noticia: "+fields.titulo.slice(0,85),"crear noticia");
    return json({ok:true,message:"Noticia enviada a revisión editorial.",pr},201);
  }
  const match=path.match(/^\/api\/news\/([a-f0-9-]+)$/i);
  if(match&&method==="PATCH"){
    const id=match[1],fields=validateArticle(body);
    const pr=await submitChange(env,cache=>{
      const article=cache.noticias.find(x=>String(x.id)===id);
      if(!article)throw new AdminError(404,"La noticia ya no existe en la versión publicada.");
      Object.assign(article,fields);return cache;
    },"CEV NOTICIAS | Editar noticia: "+fields.titulo.slice(0,85),"editar noticia "+id);
    return json({ok:true,message:"Cambios enviados a revisión editorial.",pr});
  }
  if(match&&method==="DELETE"){
    const id=match[1];
    const pr=await submitChange(env,cache=>{
      const before=cache.noticias.length;
      cache.noticias=cache.noticias.filter(x=>String(x.id)!==id);
      if(cache.noticias.length===before)throw new AdminError(404,"La noticia ya no existe en la versión publicada.");
      return cache;
    },"CEV NOTICIAS | Retirar noticia "+id,"solicitar retiro de noticia "+id);
    return json({ok:true,message:"Retiro enviado a revisión editorial.",pr});
  }
  const review=path.match(/^\/api\/reviews\/(\d+)\/(approve|reject)$/);
  if(review&&method==="POST"){
    const number=Number(review[1]),action=review[2];
    const pr=await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+number,env);
    if(pr.state!=="open"||!pr.base||pr.base.ref!==MAIN||!pr.head||!managedBranch(pr.head.ref)) throw new AdminError(403,"La solicitud no pertenece a la cola editorial de CEV NOTICIAS.");
    if(action==="approve"){
      const result=await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+number+"/merge",env,"PUT",{merge_method:"squash",commit_title:"Publicación editorial CEV NOTICIAS"});
      if(!result.merged)throw new AdminError(409,"GitHub no pudo fusionar la propuesta. Revisa los conflictos.");
      try{await gh("/repos/"+OWNER+"/"+REPO+"/git/refs/heads/"+pr.head.ref,env,"DELETE")}catch(_){}
      return json({ok:true,message:"Propuesta aprobada y fusionada. GitHub Pages iniciará la publicación."});
    }
    await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+number,env,"PATCH",{state:"closed"});
    try{await gh("/repos/"+OWNER+"/"+REPO+"/git/refs/heads/"+pr.head.ref,env,"DELETE")}catch(_){}
    return json({ok:true,message:"Propuesta rechazada y cerrada."});
  }
  return json({error:"Ruta no encontrada."},404);
}

export default {
  async fetch(request,env,ctx) {
    if(!ctx.access)return new Response("Acceso protegido requerido.",{status:403,headers:{"cache-control":"no-store","x-robots-tag":"noindex, nofollow"}});
    let identity=null;
    try{identity=await ctx.access.getIdentity()}catch(_){}
    if(!identity)return new Response("No se pudo verificar la identidad de acceso.",{status:403,headers:{"cache-control":"no-store"}});
    const path=new URL(request.url).pathname;
    if(!path.startsWith("/api/"))return new Response(dashboardHtml,{headers:{
      "content-type":"text/html; charset=utf-8","cache-control":"no-store, private","x-content-type-options":"nosniff",
      "x-frame-options":"DENY","referrer-policy":"strict-origin-when-cross-origin","x-robots-tag":"noindex, nofollow",
      "content-security-policy":"default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    }});
    try{return await api(request,env,identity)}catch(e){
      if(e instanceof AdminError)return json({error:e.message,detail:e.detail},e.status);
      return json({error:"Error interno. Revisa la configuración del Worker."},500);
    }
  }
};
