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
function dateISOCO() {
  const p={};
  new Intl.DateTimeFormat("en-CA",{timeZone:"America/Bogota",year:"numeric",month:"2-digit",day:"2-digit"})
    .formatToParts(new Date()).forEach(x=>p[x.type]=x.value);
  return p.year+"-"+p.month+"-"+p.day;
}
function managedBranch(b) { return b==="revision-editorial/noticias-pendientes" || String(b||"").startsWith("revision-editorial/noticias-pendientes-") || String(b||"").startsWith("revision-admin/") || String(b||"").startsWith("feature/centro-diagnostico-automatico"); }

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
async function registrarFuentesDePropuestaRechazada(env,branch) {
  const base="/repos/"+OWNER+"/"+REPO+"/contents/";
  const [principal,propuesta,archivoEstado]=await Promise.all([
    gh(base+"cache.json?ref="+MAIN,env),
    gh(base+"cache.json?ref="+encodeURIComponent(branch),env),
    gh(base+"automation_state.json?ref="+MAIN,env)
  ]);
  if(!principal.content||!propuesta.content||!archivoEstado.content) return 0;
  const cachePrincipal=JSON.parse(decode64(principal.content));
  const cachePropuesta=JSON.parse(decode64(propuesta.content));
  const estado=JSON.parse(decode64(archivoEstado.content));
  const idsPublicados=new Set((cachePrincipal.noticias||[]).map(n=>String(n.id||"")));
  const idsBrevesPublicados=new Set((cachePrincipal.breves||[]).map(n=>String(n.id||"")));
  const articulosNuevos=(cachePropuesta.noticias||[]).filter(n=>n.id&&!idsPublicados.has(String(n.id)));
  const brevesNuevos=(cachePropuesta.breves||[]).filter(n=>n.id&&!idsBrevesPublicados.has(String(n.id)));
  const urlsNuevas=[
    ...articulosNuevos.flatMap(n=>(n.fuentes||[]).map(f=>String(f.url||"").trim())),
    ...brevesNuevos.flatMap(n=>(n.fuentes||[]).map(f=>String(f.url||"").trim()))
  ].filter(u=>u.startsWith("https://"));
  const existentes=Array.isArray(estado.fuentes_descartadas)?estado.fuentes_descartadas:[];
  const ahora=new Date().toISOString();
  const porUrl=new Map(existentes.filter(x=>x&&x.url).map(x=>[String(x.url),x]));
  for(const url of urlsNuevas) porUrl.set(url,{url,fecha:ahora});
  estado.fuentes_descartadas=[...porUrl.values()].slice(-500);
  if(urlsNuevas.length){
    await gh(base+"automation_state.json",env,"PUT",{
      message:"Registrar fuentes de propuestas editoriales rechazadas",
      content:encode64(JSON.stringify(estado,null,2)+"\n"),
      sha:archivoEstado.sha,
      branch:MAIN
    });
  }
  return urlsNuevas.length;
}

async function reviews(env) {
  const all=await gh("/repos/"+OWNER+"/"+REPO+"/pulls?state=open&per_page=100&sort=created&direction=desc",env);
  const managed=all.filter(p=>p.base&&p.base.ref===MAIN&&p.head&&managedBranch(p.head.ref)).slice(0,25);
  return Promise.all(managed.map(async p=>{
    let detail=p,files=[];
    try{detail=await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+p.number,env)}catch(_){}
    try{files=await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+p.number+"/files?per_page=100",env)}catch(_){}
    const fileRows=(Array.isArray(files)?files:[]).map(f=>({
      filename:String(f.filename||"archivo"),
      status:String(f.status||"modified"),
      additions:Number(f.additions)||0,
      deletions:Number(f.deletions)||0,
      changes:Number(f.changes)||0
    }));
    const add=Number(detail.additions),del=Number(detail.deletions),body=String(detail.body||p.body||"");
    const proposedTitles=[...body.matchAll(/^###\s+(.+)$/gm)].map(m=>m[1].trim()).filter(Boolean).slice(0,20);
    return {
      number:p.number,title:detail.title||p.title,body,url:p.html_url,
      branch:p.head.ref,createdAt:detail.created_at||p.created_at,
      updatedAt:detail.updated_at||p.updated_at||p.created_at,
      author:p.user?p.user.login:"GitHub",draft:Boolean(detail.draft),
      additions:Number.isFinite(add)?add:fileRows.reduce((sum,x)=>sum+x.additions,0),
      deletions:Number.isFinite(del)?del:fileRows.reduce((sum,x)=>sum+x.deletions,0),
      changedFiles:Number(detail.changed_files)||fileRows.length,
      statsAvailable:(Number.isFinite(add)&&Number.isFinite(del)&&Number(detail.changed_files)>0)||fileRows.length>0,
      files:fileRows.slice(0,20),proposedTitles
    };
  }));
}
async function readRSSRadar(env,fallback) {
  const base=fallback&&typeof fallback==="object"?fallback:{};
  try {
    const f=await gh("/repos/"+OWNER+"/"+REPO+"/contents/radar_rss.json?ref="+MAIN,env);
    if(!f.content||f.encoding!=="base64") throw new Error("Archivo RSS sin contenido.");
    const data=JSON.parse(decode64(f.content));
    return {
      titulares_rss:Array.isArray(data.titulares_rss)?data.titulares_rss:(Array.isArray(base.titulares_rss)?base.titulares_rss:[]),
      estado_fuentes:Array.isArray(data.estado_fuentes)?data.estado_fuentes:(Array.isArray(base.estado_fuentes)?base.estado_fuentes:[]),
      ultima_actualizacion:data.ultima_actualizacion||base.ultima_actualizacion||null
    };
  } catch (_) {
    return {
      titulares_rss:Array.isArray(base.titulares_rss)?base.titulares_rss:[],
      estado_fuentes:Array.isArray(base.estado_fuentes)?base.estado_fuentes:[],
      ultima_actualizacion:base.ultima_actualizacion||null
    };
  }
}

async function readAutomationState(env) {
  const defaults = {
    fecha_solicitudes_groq:"",
    solicitudes_groq:0,
    ultima_solicitud_groq:"",
    fecha_articulos_dia:"",
    articulos_generados_dia:0,
    limite_articulos_diario:30,
    limite_breves_diario:30,
    breves_generados_dia:0,
    fecha_breves_dia:"",
    limite_breves_ejecucion:3,
    limite_solicitudes_diario:60,
    limite_articulos_ejecucion:5
  };
  try {
    const f=await gh("/repos/"+OWNER+"/"+REPO+"/contents/automation_state.json?ref="+MAIN,env);
    if(!f.content||f.encoding!=="base64") return defaults;
    const data=JSON.parse(decode64(f.content));
    return Object.assign({},defaults,data);
  } catch (_) {
    return defaults;
  }
}

async function readFeeds(env) {
  const f=await gh("/repos/"+OWNER+"/"+REPO+"/contents/feeds.json?ref="+MAIN,env);
  if(!f.content||f.encoding!=="base64") throw new AdminError(502,"No se pudo leer feeds.json.");
  let data;
  try{data=JSON.parse(decode64(f.content))}catch(_){throw new AdminError(502,"feeds.json no contiene JSON válido.")}
  if(Array.isArray(data)) return data;
  return Array.isArray(data.feeds)?data.feeds:[];
}
async function automationRuns() {
  try {
    const path="/repos/"+OWNER+"/"+REPO+"/actions/workflows/actualizar.yml/runs?per_page=6";
    const response=await fetch(API+path,{headers:{"accept":"application/vnd.github+json","user-agent":"CEVNoticias-Admin/1.0"}});
    if(!response.ok) return [];
    const data=await response.json();
    return (data.workflow_runs||[]).map(run=>({
      id:run.id,
      status:run.status||"unknown",
      conclusion:run.conclusion||"",
      createdAt:run.created_at||"",
      updatedAt:run.updated_at||"",
      branch:run.head_branch||"",
      event:run.event||"",
      url:run.html_url||""
    }));
  } catch(_) {
    return [];
  }
}
async function submitChange(env,mutate,title,description,imageUpload) {
  const pending=await reviews(env);
  if(pending.length) throw new AdminError(409,"Ya existe una propuesta editorial pendiente. Resuélvela antes de crear otra.",{pending});
  const ref1=await gh("/repos/"+OWNER+"/"+REPO+"/git/ref/heads/"+MAIN,env);
  const cached=await readCache(env);
  const ref2=await gh("/repos/"+OWNER+"/"+REPO+"/git/ref/heads/"+MAIN,env);
  if(ref1.object.sha!==ref2.object.sha) throw new AdminError(409,"El repositorio cambió durante la operación. Actualiza el panel e inténtalo otra vez.");
  const branch="revision-admin/panel-"+Date.now()+"-"+crypto.randomUUID().slice(0,8);
  await gh("/repos/"+OWNER+"/"+REPO+"/git/refs",env,"POST",{ref:"refs/heads/"+branch,sha:ref1.object.sha});
  let uploadedImageUrl="";
  try {
    if(imageUpload){const types={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"},ext=types[String(imageUpload.type||"")];if(!ext||typeof imageUpload.data!=="string"||imageUpload.data.length>890000)throw new AdminError(400,"Imagen no válida o demasiado grande. Usa JPG, PNG o WebP de máximo 650 KB.");const imagePath="assets/editorial-news/"+crypto.randomUUID()+"."+ext;await gh("/repos/"+OWNER+"/"+REPO+"/contents/"+imagePath,env,"PUT",{message:"Panel CEV: subir fotografía editorial",content:imageUpload.data,branch});uploadedImageUrl="https://raw.githubusercontent.com/"+OWNER+"/"+REPO+"/"+MAIN+"/"+imagePath;}
    const updated=mutate(cached.data,uploadedImageUrl);
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
  if(content.split(/\s+/).filter(Boolean).length<300) throw new AdminError(400,"El artículo debe tener al menos 300 palabras.");
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
  const add = (severity, code, message, id, remediation) => { const article=articles.find(x=>String(x.id)===String(id)); findings.push({severity,code,message,articleId:id||null,articleTitle:article?String(article.titulo||"Sin titular"):"",remediation:remediation||"Abre la publicación y revisa sus datos editoriales."}); };
  const articles = Array.isArray(cache.noticias) ? cache.noticias : [];
  for (const n of articles) {
    const id = String(n.id || ""), title = String(n.titulo || "").trim();
    const key = title.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g," ").trim();
    if (!title) add("critical","missing_title","Noticia sin titular",id,"Añade un titular claro y verificable desde el editor.");
    if (key && titles.has(key)) add("warning","duplicate_title","Titular idéntico al registro "+titles.get(key),id,"Comprueba si es una noticia duplicada. Si es la misma información, conserva un solo registro o diferencia el titular si son hechos distintos.");
    else if (key) titles.set(key,id);
    const image = String(n.imagen || "").trim();
    if (!image) add("warning","missing_image","Falta imagen periodística principal.",id,"En el editor, añade una fotografía real relacionada con el titular y completa autor, fuente, página de origen y licencia. No uses una imagen genérica ni una portada con texto.");
    else {
      try { if (new URL(image).protocol !== "https:") add("critical","image_not_https","La imagen no usa HTTPS.",id,"Sustituye la URL por el enlace HTTPS de la fotografía y verifica que la licencia permita su uso."); }
      catch (_) { add("critical","invalid_image","URL de imagen no válida.",id,"Introduce una URL directa y válida de una fotografía pertinente; completa también sus datos de atribución."); }
      if (images.has(image)) add("warning","duplicate_image","La imagen se repite en otra noticia.",id,"Comprueba si la fotografía corresponde realmente a esta noticia. Si no, reemplázala por una imagen específica y autorizada.");
      else images.set(image,id);
    }
    const sources = Array.isArray(n.fuentes) ? n.fuentes : [];
    if (!sources.length) add("critical","missing_sources","Noticia sin fuentes registradas.",id,"Añade la fuente original con nombre, titular de referencia y URL HTTPS. No publiques afirmaciones sin respaldo verificable.");
    if (sources.length === 1) add("warning","single_source","Noticia con una sola fuente; requiere corroboración.",id,"Busca una segunda fuente independiente que confirme los datos. Añádela en el segundo bloque de fuentes del editor.");
    for (const source of sources) {
      try { if (new URL(source.url).protocol !== "https:") add("critical","invalid_source","Fuente sin HTTPS.",id,"Reemplaza el enlace por la dirección HTTPS oficial de la fuente y verifica que abra correctamente."); }
      catch (_) { add("critical","invalid_source","URL de fuente no válida.",id,"Corrige la URL de la fuente y comprueba que corresponda al documento o noticia citada."); }
    }
    if (String(n.resumen || "").trim().length < 40) add("warning","short_summary","Resumen inferior a 40 caracteres.",id,"Amplía el resumen para que explique el hecho principal con al menos 40 caracteres.");
    if (String(n.contenido || "").trim().split(/\s+/).filter(Boolean).length < 300) add("warning","short_content","Contenido inferior a 300 palabras.",id,"Completa el contenido con contexto, datos, antecedentes y atribución. El editor exige al menos 300 palabras.");
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
  if(!env.GITHUB_TOKEN) return {configured:false,user:identity.email||identity.name||"Administrador",news:[],reviews:[],feeds:[],feedStatus:[],automation:[]};
  const r=await Promise.all([readCache(env),reviews(env),readFeeds(env),automationRuns(),readAutomationState(env)]);
  const radar=await readRSSRadar(env,r[0].data);
  return {
    configured:true,
    user:identity.email||identity.name||"Administrador",
    news:r[0].data.noticias,
    // El radar se lee desde un archivo independiente: no depende de aprobar artículos.
    rssHeadlines:radar.titulares_rss,
    reviews:r[1],
    feeds:r[2].map(f=>({nombre:String(f.nombre||"Fuente"),url:String(f.url||""),zona:String(f.zona||"Nacional / internacional")})),
    feedStatus:(radar.estado_fuentes||[]).map(x=>{
      const sourceState=String(x.estado||"").toLowerCase();
      const detail=String(x.detalle||x.error||"");
      const normalized=sourceState==="correcto"?"ok":
        (sourceState==="sin_novedades"||detail.toLowerCase().includes("no contiene entradas")?"sin_entradas":"error");
      return {
        nombre:String(x.nombre||"Fuente RSS"),estado:normalized,
        entradas_rss:Number(x.titulares)||0,titulares_vigentes:Number(x.titulares)||0,
        error:normalized==="error"?detail:"",
        ultima_consulta:x.ultima_consulta||radar.ultima_actualizacion||null
      };
    }),
    headlineAIConfigured:Boolean(env.GROQ_API_KEY),
    automation:r[3],
    automationLimits:{
      articlesToday:r[4].fecha_articulos_dia===dateISOCO()?(Number(r[4].articulos_generados_dia)||0):0,
      dailyArticleLimit:Number(r[4].limite_articulos_diario)||30,
      briefsToday:r[4].fecha_breves_dia===dateISOCO()?(Number(r[4].breves_generados_dia)||0):0,
      dailyBriefLimit:Number(r[4].limite_breves_diario)||30,
      maxBriefsPerRun:Number(r[4].limite_breves_ejecucion)||3,
      dailyRequests:r[4].fecha_solicitudes_groq===dateISOCO()?(Number(r[4].solicitudes_groq)||0):0,
      dailyRequestLimit:Number(r[4].limite_solicitudes_diario)||60,
      maxArticlesPerRun:Number(r[4].limite_articulos_ejecucion)||5,
      articleDate:r[4].fecha_articulos_dia||"",
      requestDate:r[4].fecha_solicitudes_groq||"",
      lastRequest:r[4].ultima_solicitud_groq||""
    },
    rssCount:radar.titulares_rss.length,
    latestUpdate:radar.ultima_actualizacion,
    latestNewsUpdate:r[0].data.ultima_actualizacion||null
  };
}
async function publicationStatus(env,sha) {
  const response=await gh("/repos/"+OWNER+"/"+REPO+"/actions/runs?head_sha="+encodeURIComponent(sha)+"&per_page=20",env);
  const runs=(response.workflow_runs||[]).filter(run=>run.path===".github/workflows/publicar.yml"&&run.head_branch==="main");
  if(!runs.length) return {state:"queued",message:"Esperando que GitHub inicie la publicación."};
  runs.sort((a,b)=>String(b.created_at||"").localeCompare(String(a.created_at||"")));
  const run=runs[0];
  if(run.status!=="completed") return {state:"running",message:"La web se está reconstruyendo y publicando.",runUrl:run.html_url||""};
  return {
    state:run.conclusion==="success"?"success":"failure",
    message:run.conclusion==="success"?"La publicación de la web terminó correctamente.":"GitHub Actions no pudo completar la publicación.",
    conclusion:run.conclusion||"",
    runUrl:run.html_url||""
  };
}


async function downloadPhoto(urlValue,nameValue){
 const allowedHosts=new Set(["thumb.wikimedia.org","upload.wikimedia.org","raw.githubusercontent.com","cevnoticias.com","www.cevnoticias.com","images.unsplash.com"]);
 let current;
 try{current=new URL(String(urlValue||""))}catch(_){throw new AdminError(400,"La dirección de la fotografía no es válida.");}
 if(current.protocol!=="https:"||!allowedHosts.has(current.hostname.toLowerCase()))throw new AdminError(400,"Por seguridad, solo se pueden descargar fotografías de las fuentes autorizadas.");
 let response=null;
 for(let hop=0;hop<4;hop++){
  if(current.protocol!=="https:"||!allowedHosts.has(current.hostname.toLowerCase()))throw new AdminError(400,"La fotografía redirige a un dominio no autorizado.");
  response=await fetch(current.toString(),{redirect:"manual",headers:{"accept":"image/avif,image/webp,image/apng,image/*,*/*;q=0.8","user-agent":"CEVNoticias-Admin/1.0"}});
  if([301,302,303,307,308].includes(response.status)){
   const location=response.headers.get("location");
   if(!location)throw new AdminError(502,"La fuente no entregó una redirección válida.");
   current=new URL(location,current);
   continue;
  }
  break;
 }
 if(!response||[301,302,303,307,308].includes(response.status))throw new AdminError(502,"La fotografía tiene demasiadas redirecciones.");
 if(!response.ok)throw new AdminError(502,"No se pudo descargar la fotografía desde su fuente.");
 const type=String(response.headers.get("content-type")||"").split(";")[0].toLowerCase();
 const ext={"image/jpeg":"jpg","image/png":"png","image/webp":"webp","image/gif":"gif"}[type];
 if(!ext)throw new AdminError(415,"La dirección no devolvió un archivo JPG, PNG, WebP o GIF.");
 const length=Number(response.headers.get("content-length")||0);
 if(length>15728640)throw new AdminError(413,"La fotografía supera el límite de 15 MB.");
 const bytes=await response.arrayBuffer();
 if(!bytes.byteLength||bytes.byteLength>15728640)throw new AdminError(413,"La fotografía está vacía o supera el límite de 15 MB.");
 const base=String(nameValue||"fotografia").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9_-]+/gi,"-").replace(/^-+|-+$/g,"").slice(0,64)||"fotografia";
 return new Response(bytes,{status:200,headers:{
  "content-type":type,
  "content-length":String(bytes.byteLength),
  "content-disposition":'attachment; filename="'+base+"."+ext+'"',
  "cache-control":"no-store, private",
  "x-content-type-options":"nosniff"
 }});
}


async function createHeadlineOptions(body,env) {
  if(!env.GROQ_API_KEY) throw new AdminError(503,"No está activada la IA de titulares. Agrega el secreto GROQ_API_KEY en Cloudflare Workers → cev-admin → Settings → Variables and Secrets.");
  const title=String(body.titulo||"").trim(),summary=String(body.resumen||"").trim();
  const content=String(body.contenido||"").trim().slice(0,8500);
  const category=String(body.categoria||"").trim(),tone=String(body.estilo||"impact").trim();
  const toneText={
    impact:"Picante y profesional: directo, contundente y con gancho periodístico, sin sensacionalismo ni exageraciones.",
    inform:"Informativo: neutral, preciso, claro y centrado en el hecho comprobado.",
    curious:"Intriga periodística: despierta interés con una pregunta o un ángulo relevante, sin ocultar información ni insinuar hechos no demostrados."
  }[tone]||"Picante y profesional: directo, contundente y con gancho periodístico, sin sensacionalismo ni exageraciones.";
  if(title.length<12||summary.length<30||content.length<100) throw new AdminError(400,"La noticia no tiene suficiente contexto para proponer titulares.");
  const prompt=[
    "Redacta cinco versiones realmente distintas del titular de una noticia para un medio digital colombiano.",
    "Cada titular debe cambiar la construcción sintáctica, el orden de la información y el ángulo narrativo; no repitas el original con un sufijo.",
    "Estilo solicitado: "+toneText,
    "Usa exclusivamente hechos expresamente presentes en el título, resumen o texto proporcionados.",
    "No inventes cifras, fechas, lugares, personas, declaraciones, causas, consecuencias ni acusaciones.",
    "No conviertas hipótesis en hechos. No uses comillas si no existe una cita textual verificable.",
    "Cada titular debe tener entre 45 y 125 caracteres, ser legible y funcionar por sí solo.",
    "Evita que las cinco opciones comiencen con la misma estructura.",
    "Devuelve exclusivamente JSON válido con una propiedad opciones que contenga exactamente cinco titulares.",
    "",
    "CATEGORÍA: "+category,
    "TITULAR ORIGINAL: "+title,
    "RESUMEN: "+summary,
    "CONTENIDO DE LA NOTICIA: "+content
  ].join("\n");
  let response;
  try{
    response=await fetch("https://api.groq.com/openai/v1/chat/completions",{
      method:"POST",
      headers:{"authorization":"Bearer "+env.GROQ_API_KEY,"content-type":"application/json"},
      body:JSON.stringify({
        model:"openai/gpt-oss-20b",
        messages:[
          {role:"system",content:"Eres editor de titulares de CEV NOTICIAS. Prioriza fidelidad factual, claridad y variedad real de redacción. Nunca inventes información. Devuelve JSON válido."},
          {role:"user",content:prompt}
        ],
        response_format:{
          type:"json_schema",
          json_schema:{
            name:"headline_options",strict:true,
            schema:{
              type:"object",
              properties:{opciones:{type:"array",items:{type:"string"},minItems:5,maxItems:5}},
              required:["opciones"],additionalProperties:false
            }
          }
        },
        reasoning_format:"hidden",reasoning_effort:"low",
        temperature:0.7,max_completion_tokens:1000
      })
    });
  }catch(_){throw new AdminError(502,"No fue posible conectar con el servicio de generación de titulares.");}
  if(!response.ok){
    if(response.status===401||response.status===403)throw new AdminError(503,"Groq rechazó la clave GROQ_API_KEY configurada en Cloudflare.");
    if(response.status===429)throw new AdminError(503,"Se alcanzó temporalmente el límite de generación de titulares. Inténtalo más tarde.");
    throw new AdminError(502,"El servicio de titulares no pudo generar las alternativas en este momento.");
  }
  let payload;
  try{payload=await response.json()}catch(_){throw new AdminError(502,"El servicio de titulares devolvió una respuesta no válida.");}
  let parsed;
  try{parsed=JSON.parse(String(payload?.choices?.[0]?.message?.content||""))}
  catch(_){throw new AdminError(502,"No se pudo interpretar la respuesta del generador de titulares.");}
  const original=title.toLowerCase().replace(/\\s+/g," ").trim();
  const options=[...new Set((Array.isArray(parsed.opciones)?parsed.opciones:[])
    .map(x=>String(x||"").trim())
    .filter(x=>x.length>=35&&x.length<=140&&x.toLowerCase().replace(/\\s+/g," ").trim()!==original))].slice(0,5);
  if(options.length<3)throw new AdminError(502,"El generador no produjo suficientes titulares distintos. Vuelve a intentarlo.");
  return {ok:true,opciones:options,modelo:"openai/gpt-oss-20b"};
}

async function api(request,env,identity) {
  const url=new URL(request.url),path=url.pathname,method=request.method.toUpperCase();
  if(method==="GET"&&path==="/api/dashboard") return json(await dashboard(env,identity));
  if(method==="GET"&&path==="/api/photo-download") return await downloadPhoto(url.searchParams.get("url"),url.searchParams.get("name"));
  const deploymentMatch=path.match(/^\/api\/deployments\/([a-f0-9]{40})$/i);
  if(method==="GET"&&deploymentMatch) return json(await publicationStatus(env,deploymentMatch[1]));
  if(method==="GET"&&path==="/api/diagnostics") { const r=await readCache(env); return json(runDiagnostics(r.data)); }
  if(method==="POST"&&path==="/api/diagnostics/repair") { const r=await readCache(env); const count=normalizeSafeFields(r.data); if(!count) { const diag=runDiagnostics(r.data); return json({ok:true,changed:0,manualFindings:diag.findings.length,message:"No hay cambios de formato técnico pendientes. Las incidencias detectadas requieren revisión editorial: abre cada publicación con el botón de lápiz, añade o cambia la fotografía y completa sus fuentes según corresponda."}); } const pr=await submitChange(env,(cache,imageUrl)=>{normalizeSafeFields(cache);return cache;},"CEV NOTICIAS | Normalización técnica segura","normalización técnica segura"); return json({ok:true,changed:count,pr,message:"Propuesta de reparación técnica creada. Revisa y aprueba la solicitud antes de publicar."}); }
  if(method==="GET"&&path==="/api/health") {
    if(!env.GITHUB_TOKEN)return json({ok:false,message:"Falta configurar GITHUB_TOKEN."},503);
    await gh("/repos/"+OWNER+"/"+REPO,env);return json({ok:true,repository:OWNER+"/"+REPO});
  }
  if(method==="POST"&&path==="/api/headlines"){
    if(request.headers.get("origin")!==ORIGIN)return json({error:"Origen no autorizado."},403);
    let body={};try{body=await request.json()}catch(_){throw new AdminError(400,"El cuerpo de la solicitud no contiene JSON válido.");}
    return json(await createHeadlineOptions(body,env));
  }
  if(!["POST","PATCH","DELETE"].includes(method)) return json({error:"Ruta no encontrada."},404);
  if(request.headers.get("origin")!==ORIGIN) return json({error:"Origen no autorizado."},403);
  let body={};
  if(method!=="DELETE"){
    if(Number(request.headers.get("content-length")||0)>1200000)throw new AdminError(413,"El contenido supera el tamaño permitido.");
    try{body=await request.json()}catch(_){throw new AdminError(400,"El cuerpo de la solicitud no contiene JSON válido.")}
  }
  if(method==="POST"&&path==="/api/news"){
    const fields=validateArticle(body.imagenUpload?Object.assign({},body,{imagen:"https://image-upload.pending.invalid/photo"}):body);
    const pr=await submitChange(env,(cache,imageUrl)=>{
      const id=crypto.randomUUID().replace(/-/g,"").slice(0,16);
      if(imageUrl)fields.imagen=imageUrl;cache.noticias.unshift(Object.assign({id,fecha:dateCO(),imagen_busqueda_intentada:false,imagen_instagram:"",imagen_instagram_tipo:"",descripcion_instagram:""},fields));
      return cache;
    },"CEV NOTICIAS | Nueva noticia: "+fields.titulo.slice(0,85),"crear noticia",body.imagenUpload);
    return json({ok:true,message:"Noticia enviada a revisión editorial.",pr},201);
  }
  const match=path.match(/^\/api\/news\/([a-f0-9-]+)$/i);
  if(match&&method==="PATCH"){
    const id=match[1],fields=validateArticle(body.imagenUpload?Object.assign({},body,{imagen:"https://image-upload.pending.invalid/photo"}):body);
    const pr=await submitChange(env,(cache,imageUrl)=>{
      const article=cache.noticias.find(x=>String(x.id)===id);
      if(!article)throw new AdminError(404,"La noticia ya no existe en la versión publicada.");
      if(imageUrl)fields.imagen=imageUrl;Object.assign(article,fields);return cache;
    },"CEV NOTICIAS | Editar noticia: "+fields.titulo.slice(0,85),"editar noticia "+id,body.imagenUpload);
    return json({ok:true,message:"Cambios enviados a revisión editorial.",pr});
  }
  if(match&&method==="DELETE"){
    const id=match[1];
    const pr=await submitChange(env,(cache,imageUrl)=>{
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
      return json({ok:true,message:"Propuesta aprobada y fusionada. Esperando la publicación de GitHub Pages.",deploySha:result.sha});
    }
    await gh("/repos/"+OWNER+"/"+REPO+"/pulls/"+number,env,"PATCH",{state:"closed"});
    let fuentesBloqueadas=0;
    try {
      fuentesBloqueadas=await registrarFuentesDePropuestaRechazada(env,pr.head.ref);
    } catch (_) {
      // El rechazo se mantiene; si GitHub no permite registrar el filtro,
      // el panel sigue funcionando y la cola continúa disponible.
    }
    try{await gh("/repos/"+OWNER+"/"+REPO+"/git/refs/heads/"+pr.head.ref,env,"DELETE")}catch(_){}
    return json({
      ok:true,
      message:fuentesBloqueadas
        ? "Propuesta rechazada. Sus fuentes quedan en pausa durante 72 horas para evitar que el mismo tema vuelva a la cola."
        : "Propuesta rechazada y cerrada."
    });
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
