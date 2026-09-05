// Cazador API - Cloudflare Worker
// Rutas:
//   GET  /                           -> frontend HTML
//   GET  /api/health                 -> health JSON
//   GET  /auth/github                -> login GitHub
//   GET  /auth/callback              -> cambia code por token y crea sesion
//   POST /auth/logout                -> borra sesion
//   GET  /api/me                     -> usuario + perfiles
//   POST /api/profile                -> crea/actualiza perfil
//   GET  /api/jobs?profile_id=&min=&max=&limit=  -> ofertas puntuadas
//   GET  /api/admin/users            -> listar usuarios (admin)
//   POST /api/admin/users            -> crear usuario (admin)
//   DELETE /api/admin/users/:id      -> eliminar usuario (admin)
//   GET  /api/admin/stats            -> estadisticas (admin)

import { scoreJob, type JobRow, type Profile } from "./scoring";
import { DEFAULT_PROFILE } from "./defaultProfile";

export interface Env {
  DB: D1Database;
  APP_ORIGIN: string;
  GITHUB_REDIRECT_URI: string;
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  SESSION_SECRET: string;
  ADMIN_KEY: string;
}

const COOKIE = "cazador_session";

// ---------------------------------------------------------------- Frontend HTML
const FRONTEND = `
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cazador - AI Job Matching</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0a0f;--card:#14141f;--card2:#1a1a2e;--border:#222238;--text:#e4e4ef;--muted:#71718a;--accent:#6366f1;--accent2:#818cf8;--green:#22c55e;--red:#ef4444;--orange:#f59e0b;--cyan:#06b6d4}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.container{max-width:1100px;margin:0 auto;padding:16px 20px}
a{color:var(--accent2);text-decoration:none}a:hover{text-decoration:underline}
.header{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:20px}
.logo{font-size:22px;font-weight:700;color:var(--accent2)}
.user-info{display:flex;align-items:center;gap:12px}
.user-info img{width:28px;height:28px;border-radius:50%}
.btn{padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:500;transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}.btn-primary:hover{background:var(--accent2)}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}.btn-ghost:hover{color:var(--text);border-color:var(--muted)}
.btn-sm{padding:4px 10px;font-size:12px}
.login-box{text-align:center;padding:100px 20px}
.login-box h1{font-size:40px;margin-bottom:8px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.login-box p{color:var(--muted);margin-bottom:32px;font-size:16px}
.kpi-row{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}
.kpi .num{font-size:26px;font-weight:700;color:var(--accent2)}
.kpi .label{font-size:11px;color:var(--muted);margin-top:2px;text-transform:uppercase;letter-spacing:.5px}
.kpi.green .num{color:var(--green)}
.kpi.orange .num{color:var(--orange)}
.kpi.cyan .num{color:var(--cyan)}
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:10px}
.filters label{font-size:12px;color:var(--muted)}
.filters select,.filters input{background:var(--card2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:6px;font-size:13px;outline:none}
.filters select:focus,.filters input:focus{border-color:var(--accent)}
.filters input[type=range]{width:120px;padding:0}
.range-val{font-size:12px;color:var(--accent2);min-width:30px;text-align:center}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}
.chart-card h3{font-size:13px;color:var(--muted);margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px}
.bar-chart{display:flex;flex-direction:column;gap:6px}
.bar-row{display:flex;align-items:center;gap:8px;font-size:12px}
.bar-label{width:100px;color:var(--muted);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar{height:20px;border-radius:4px;transition:width .3s;display:flex;align-items:center;padding:0 6px;font-size:10px;color:#fff;font-weight:600;min-width:24px}
.bar-blue{background:linear-gradient(90deg,var(--accent),var(--accent2))}
.bar-green{background:linear-gradient(90deg,#16a34a,var(--green))}
.bar-count{color:var(--text);min-width:50px;text-align:right}
.jobs-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.jobs-header h2{font-size:16px}
.jobs-header span{font-size:12px;color:var(--muted)}
.job{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:8px;transition:border-color .15s}
.job:hover{border-color:var(--accent)}
.job-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.job-title{font-weight:600;font-size:14px;margin-bottom:4px}
.job-title a{color:var(--text)}.job-title a:hover{color:var(--accent2)}
.job-match{font-size:20px;font-weight:700;white-space:nowrap}
.job-match.high{color:var(--green)}.job-match.mid{color:var(--accent2)}.job-match.low{color:var(--orange)}
.job-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
.job-meta span{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:3px}
.job-why{font-size:11px;color:var(--muted);margin-top:6px;padding:6px 8px;background:var(--card2);border-radius:6px;border-left:3px solid var(--accent)}
.badge{display:inline-block;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:600}
.badge-role{background:rgba(99,102,241,.15);color:var(--accent2)}
.badge-geo{background:rgba(6,182,212,.15);color:var(--cyan)}
.badge-star{background:rgba(245,158,11,.15);color:var(--orange)}
.empty{text-align:center;padding:60px 20px;color:var(--muted)}
.empty h3{margin-bottom:8px;color:var(--text)}
.loader{text-align:center;padding:60px;color:var(--muted)}
.loading-bar{width:200px;height:3px;background:var(--border);border-radius:2px;margin:12px auto;overflow:hidden}
.loading-bar::after{content:'';display:block;width:40%;height:100%;background:var(--accent);border-radius:2px;animation:slide 1s infinite}
@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(350%)}}
@media(max-width:768px){.kpi-row{grid-template-columns:repeat(2,1fr)}.charts-row{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container" id="app"><div class="loader">Loading...<div class="loading-bar"></div></div></div>
<script>
var API=location.origin;
var me=null,stats=null,jobs=[],filtered=[];



function api(p,o){try{return fetch(API+p,Object.assign({credentials:"include"},o||{})).then(function(r){if(r.status===401)return null;return r.json()})}catch(e){return Promise.resolve(null)}}

function init(){
api('/api/me').then(function(d){
if(!d||!d.user){showLogin();return}
me=d;
return Promise.all([api('/api/stats'),api('/api/jobs?limit=500')]);
}).then(function(r){
if(!r)return;
stats=r[0];
var jd=r[1];
jobs=(jd&&jd.jobs)||[];
filtered=jobs.slice();
render();
}).catch(function(){showLogin()});
}

function showLogin(){
document.getElementById('app').innerHTML='<div class="login-box"><h1>Cazador</h1><p>AI-powered job matching for public sector, enterprise sales & tech roles</p><p style="color:var(--muted);font-size:13px;margin-bottom:24px">128 ofertas pre-evaluadas · Scoring calibrado por perfil</p><a href="'+API+'/auth/github" class="btn btn-primary" style="font-size:16px;padding:14px 40px">Login with GitHub</a></div>';
}

function render(){
var u=me.user;
var h='<div class="header"><div class="logo">Cazador</div><div class="user-info"><span>'+u.login+'</span><button class="btn btn-ghost btn-sm" id="btnLogout">Logout</button></div></div>';

if(stats){
h+='<div class="kpi-row">';
h+='<div class="kpi"><div class="num">'+stats.total+'</div><div class="label">Total ofertas</div></div>';
h+='<div class="kpi green"><div class="num">'+stats.over40+'</div><div class="label">Match >= 40</div></div>';
h+='<div class="kpi cyan"><div class="num">'+stats.over60+'</div><div class="label">Match >= 60</div></div>';
h+='<div class="kpi orange"><div class="num">'+stats.over80+'</div><div class="label">Match >= 80</div></div>';
h+='<div class="kpi"><div class="num">'+stats.avgMatch+'%</div><div class="label">Avg match</div></div>';
h+='</div>';
}

if(stats&&stats.byCountry&&stats.byCountry.length){
h+='<div class="charts-row">';
h+='<div class="chart-card"><h3>Por pais</h3><div class="bar-chart">';
var maxC=Math.max.apply(null,stats.byCountry.map(function(c){return c.c}));
stats.byCountry.forEach(function(c){
var w=Math.round(c.c/maxC*100);
h+='<div class="bar-row"><div class="bar-label">'+c.country+'</div><div class="bar bar-blue" style="width:'+w+'%">'+c.c+'</div><div class="bar-count">avg '+c.avg_m+'%</div></div>';
});
h+='</div></div>';
h+='<div class="chart-card"><h3>Por rol</h3><div class="bar-chart">';
var maxR=Math.max.apply(null,stats.byRole.map(function(r){return r.c}));
stats.byRole.forEach(function(r){
var w=Math.round(r.c/maxR*100);
h+='<div class="bar-row"><div class="bar-label">'+r.role_family+'</div><div class="bar bar-green" style="width:'+w+'%">'+r.c+'</div><div class="bar-count">avg '+r.avg_m+'%</div></div>';
});
h+='</div></div>';
h+='</div>';
}

h+='<div class="filters">';
h+='<label>Keywords:</label><input type="text" id="fSearch" placeholder="titulo, empresa, rol..." style="width:200px">';
h+='<label>Pais:</label><select id="fCountry"><option value="">Todos</option></select>';
h+='<label>Match min:</label><input type="range" id="fMatch" min="0" max="90" value="0"><span class="range-val" id="fMatchVal">0</span>';
h+='<label>Rol:</label><select id="fRole"><option value="">Todos</option></select>';
h+='<label>Empresa:</label><select id="fCompany"><option value="">Todas</option></select>';
h+='<button class="btn btn-ghost btn-sm" id="btnReset">Limpiar</button>';
h+='</div>';

h+='<div class="jobs-header"><h2>Ofertas</h2><span id="jobCount">'+filtered.length+' resultados</span></div>';
h+='<div id="jobList">';
h+=renderJobs();
h+='</div>';

document.getElementById('app').innerHTML=h;
bindEvents();
}

function renderJobs(){
if(filtered.length===0)return '<div class="empty"><h3>Sin resultados</h3><p>Ajusta los filtros para ver mas ofertas.</p></div>';
var h='';
filtered.forEach(function(j){
var mc=j.match>=70?'high':j.match>=50?'mid':'low';
h+='<div class="job"><div class="job-top"><div><div class="job-title"><a href="'+(j.url||'#')+'" target="_blank">'+(j.title||'Sin titulo')+'</a></div><div class="job-meta">';
if(j.company)h+='<span>'+j.company+'</span>';
if(j.location)h+='<span>'+j.location+'</span>';
if(j.salary)h+='<span>'+j.salary+'</span>';
if(j.posted)h+='<span>'+j.posted+'</span>';
h+='<span class="badge badge-role">'+(j.roleFamily||'')+'</span>';
h+='<span class="badge badge-geo">'+countryOf(j.location)+'</span>';
h+='</div></div><div class="job-match '+mc+'">'+j.match+'%</div></div>';
if(j.why)h+='<div class="job-why">'+j.why+'</div>';
h+='</div>';
});
return h;
}

function countryOf(loc){
if(!loc)return'Other';
var l=loc.toLowerCase();
if(l.match(/netherlands|amsterdam|utrecht|rotterdam|eindhoven/))return'Netherlands';
if(l.match(/ireland|dublin/))return'Ireland';
if(l.match(/united kingdom|london|england|uk/))return'UK';
if(l.match(/germany|berlin|munich|frankfurt/))return'Germany';
if(l.match(/united arab|dubai|abu dhabi|uae/))return'UAE';
if(l.match(/switzerland|zurich|geneva/))return'Switzerland';
if(l.match(/mexico|cdmx|guadalajara/))return'Mexico';
if(l.match(/singapore/))return'Singapore';
if(l.match(/sweden|stockholm/))return'Sweden';
if(l.match(/remote/))return'Remote';
return'Other';
}

function applyFilters(){
var country=document.getElementById('fCountry').value;
var minMatch=parseInt(document.getElementById('fMatch').value)||0;
var role=document.getElementById('fRole').value;
var company=document.getElementById('fCompany').value;
var search=(document.getElementById('fSearch').value||'').toLowerCase();
filtered=jobs.filter(function(j){
if(country&&countryOf(j.location)!==country)return false;
if(j.match<minMatch)return false;
if(role&&(j.roleFamily||'')!==role)return false;
if(company&&(j.company||'')!==company)return false;
if(search){
var hay=((j.title||'')+' '+(j.company||'')+' '+(j.location||'')+' '+(j.roleFamily||'')+' '+(j.why||'')).toLowerCase();
if(hay.indexOf(search)<0)return false;
}
return true;
});
document.getElementById('jobCount').textContent=filtered.length+' resultados';
document.getElementById('jobList').innerHTML=renderJobs();
}

function populateDropdowns(){
var countries={};var roles={};var companies={};
jobs.forEach(function(j){
var c=countryOf(j.location);countries[c]=(countries[c]||0)+1;
var r=j.roleFamily||'';if(r)roles[r]=(roles[r]||0)+1;
var co=j.company||'';if(co)companies[co]=(companies[co]||0)+1;
});
var cs=document.getElementById('fCountry');
Object.keys(countries).sort(function(a,b){return countries[b]-countries[a]}).forEach(function(c){
var o=document.createElement('option');o.value=c;o.textContent=c;cs.appendChild(o);
});
var rs=document.getElementById('fRole');
Object.keys(roles).sort(function(a,b){return roles[b]-roles[a]}).forEach(function(r){
var o=document.createElement('option');o.value=r;o.textContent=r;rs.appendChild(o);
});
var co=document.getElementById('fCompany');
Object.keys(companies).sort(function(a,b){return companies[b]-companies[a]}).forEach(function(c){
var o=document.createElement('option');o.value=c;o.textContent=c+' ('+companies[c]+')';co.appendChild(o);
});
}

function bindEvents(){
document.getElementById('fSearch').addEventListener('input',applyFilters);
document.getElementById('fCountry').addEventListener('change',applyFilters);
document.getElementById('fMatch').addEventListener('input',function(){
document.getElementById('fMatchVal').textContent=this.value;
applyFilters();
});
document.getElementById('fRole').addEventListener('change',applyFilters);
document.getElementById('fCompany').addEventListener('change',applyFilters);
document.getElementById('btnReset').addEventListener('click',function(){
document.getElementById('fSearch').value='';
document.getElementById('fCountry').value='';
document.getElementById('fMatch').value=0;
document.getElementById('fMatchVal').textContent='0';
document.getElementById('fRole').value='';
document.getElementById('fCompany').value='';
filtered=jobs.slice();
applyFilters();
});
document.getElementById('btnLogout').addEventListener('click',function(){
api('/auth/logout',{method:'POST'}).then(function(){me=null;showLogin()});
});
populateDropdowns();
}

init();
</script>
</body>
</html>
`;

// --------------------------------------------------------------- helpers

function json(data: unknown, status = 200, origin?: string | null): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(origin || null),
    },
  });
}

function html(content: string): Response {
  return new Response(content, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

function corsHeaders(origin: string | null): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
  };
}

async function hmacHex(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function issueSession(githubId: number, secret: string): Promise<string> {
  const sig = await hmacHex(String(githubId), secret);
  return `${githubId}.${sig}`;
}

async function readSession(token: string | null, secret: string): Promise<number | null> {
  if (!token) return null;
  const m = token.match(/^(\d+)\.([0-9a-f]{64})$/);
  if (!m) return null;
  const [, id, sig] = m;
  const expect = await hmacHex(id, secret);
  if (expect !== sig) return null;
  return parseInt(id, 10);
}

function readCookie(req: Request): string | null {
  const cookie = req.headers.get("Cookie") || "";
  return cookie.split(";").map((c) => c.trim()).find((c) => c.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1) || null;
}

// --------------------------------------------------------------- GitHub OAuth

async function githubToken(code: string, env: Env): Promise<string | null> {
  const r = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: env.GITHUB_REDIRECT_URI,
    }),
  });
  const body = await r.text();
  console.error("githubToken response:", r.status, body.substring(0, 300));
  if (!r.ok) return null;
  try {
    const d = JSON.parse(body) as { access_token?: string; error?: string };
    if (d.error) { console.error("githubToken error:", d.error); return null; }
    return d.access_token || null;
  } catch { return null; }
}

async function githubUser(token: string): Promise<{ user: { id: number; login: string; name: string; avatar: string } | null; error?: string }> {
  let r: Response;
  try {
    r = await fetch("https://api.github.com/user", {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json", "User-Agent": "Cazador-App" },
    });
  } catch (e: any) {
    return { user: null, error: `fetch failed: ${e.message}` };
  }
  const body = await r.text().catch(() => "");
  if (!r.ok) return { user: null, error: `github ${r.status}: ${body.substring(0, 200)}` };
  try {
    const d = JSON.parse(body) as { id: number; login: string; name?: string; avatar_url?: string };
    return { user: { id: d.id, login: d.login, name: d.name || d.login, avatar: d.avatar_url || "" } };
  } catch (e: any) {
    return { user: null, error: `parse error: ${e.message}` };
  }
}

async function defaultProfile(): Promise<Profile> {
  return JSON.parse(JSON.stringify(DEFAULT_PROFILE));
}

// --------------------------------------------------------------- handlers

async function handleAuthGithub(env: Env): Promise<Response> {
  const state = crypto.randomUUID();
  const url =
    `https://github.com/login/oauth/authorize?client_id=${env.GITHUB_CLIENT_ID}` +
    `&redirect_uri=${encodeURIComponent(env.GITHUB_REDIRECT_URI)}` +
    `&scope=read:user&state=${state}`;
  return Response.redirect(url, 302);
}

async function handleAuthCallback(req: Request, env: Env, origin: string | null): Promise<Response> {
  const u = new URL(req.url);
  const code = u.searchParams.get("code");
  if (!code) return json({ error: "missing code" }, 400);
  const token = await githubToken(code, env);
  if (!token) return json({ error: "github token failed" }, 401);
  const { user: gh, error: ghErr } = await githubUser(token);
  if (!gh) return json({ error: "github user failed", detail: ghErr }, 401);

  // Solo permite login si el usuario esta pre-autorizado en la tabla users
  const existing = await env.DB.prepare("SELECT id FROM users WHERE github_id = ?").bind(gh.id).first<{ id: number }>();
  if (!existing) {
    const redirectUrl = new URL(env.APP_ORIGIN);
    redirectUrl.searchParams.set("error", "not_authorized");
    const headers = corsHeaders(origin);
    headers["Location"] = redirectUrl.toString();
    return new Response(null, { status: 302, headers });
  }

  // Actualiza datos del usuario
  await env.DB.prepare("UPDATE users SET login = ?, name = ?, avatar_url = ? WHERE id = ?")
    .bind(gh.login, gh.name, gh.avatar, existing.id).run();

  // Si no tiene perfil default, crea uno
  const profile = await env.DB.prepare("SELECT id FROM profiles WHERE user_id = ? AND is_default = 1").bind(existing.id).first<{ id: number }>();
  if (!profile) {
    const def = await defaultProfile();
    await env.DB.prepare(
      "INSERT INTO profiles (user_id, name, role_taxonomy, anti_identity, hard_reject, domain_keywords, skills_keywords, geography, seniority, spoken_languages, min_match, max_match, is_default) VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
    ).bind(existing.id, JSON.stringify(def.role_taxonomy), JSON.stringify(def.anti_identity),
      JSON.stringify(def.hard_reject), JSON.stringify(def.domain_keywords),
      JSON.stringify(def.skills_keywords), JSON.stringify(def.geography),
      JSON.stringify(def.seniority), JSON.stringify(def.spoken_languages),
      def.min_match, def.max_match).run();
  }

  const session = await issueSession(gh.id, env.SESSION_SECRET);
  const headers = corsHeaders(origin);
  headers["Location"] = env.APP_ORIGIN;
  headers["Set-Cookie"] = `${COOKIE}=${session}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000`;
  return new Response(null, { status: 302, headers });
}

function logoutCookie(origin: string | null): Response {
  const headers = corsHeaders(origin);
  headers["Set-Cookie"] = `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
  return new Response(null, { status: 204, headers });
}

async function handleMe(env: Env, githubId: number): Promise<Response> {
  const user = await env.DB.prepare("SELECT id, github_id, login, name, avatar_url FROM users WHERE github_id = ?")
    .bind(githubId).first<{ id: number }>();
  if (!user) return json({ error: "user not found" }, 404);
  const profiles = await env.DB.prepare("SELECT id, name, role_taxonomy, anti_identity, hard_reject, domain_keywords, skills_keywords, geography, seniority, spoken_languages, min_match, max_match, is_default FROM profiles WHERE user_id = ?")
    .bind(user.id).all();
  if (profiles.results.length === 0) {
    const def = await defaultProfile();
    await env.DB.prepare(
      "INSERT INTO profiles (user_id, name, role_taxonomy, anti_identity, hard_reject, domain_keywords, skills_keywords, geography, seniority, spoken_languages, min_match, max_match, is_default) VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
    ).bind(user.id, def.role_taxonomy, def.anti_identity, def.hard_reject, def.domain_keywords, def.skills_keywords, def.geography, def.seniority, def.spoken_languages, def.min_match, def.max_match).run();
    profiles.results.push({ id: 1, name: "default", role_taxonomy: def.role_taxonomy, anti_identity: def.anti_identity, hard_reject: def.hard_reject, domain_keywords: def.domain_keywords, skills_keywords: def.skills_keywords, geography: def.geography, seniority: def.seniority, spoken_languages: def.spoken_languages, min_match: def.min_match, max_match: def.max_match, is_default: 1 });
  }
  return json({ user, profiles: profiles.results });
}

async function handleProfile(req: Request, env: Env, githubId: number): Promise<Response> {
  const body = (await req.json()) as {
    id?: number;
    name?: string;
    role_taxonomy?: unknown;
    anti_identity?: unknown;
    hard_reject?: unknown;
    domain_keywords?: unknown;
    skills_keywords?: unknown;
    geography?: unknown;
    seniority?: unknown;
    spoken_languages?: string[];
    min_match?: number;
    max_match?: number;
  };
  const user = await env.DB.prepare("SELECT id FROM users WHERE github_id = ?").bind(githubId).first<{ id: number }>();
  if (!user) return json({ error: "user not found" }, 401);
  const sets = {
    role_taxonomy: JSON.stringify(body.role_taxonomy ?? {}),
    anti_identity: JSON.stringify(body.anti_identity ?? { reject_title_patterns: [] }),
    hard_reject: JSON.stringify(body.hard_reject ?? {}),
    domain_keywords: JSON.stringify(body.domain_keywords ?? { keywords: [] }),
    skills_keywords: JSON.stringify(body.skills_keywords ?? []),
    geography: JSON.stringify(body.geography ?? {}),
    seniority: JSON.stringify(body.seniority ?? { bonus: [], penalty: [] }),
    spoken_languages: JSON.stringify(body.spoken_languages ?? ["english"]),
    min_match: body.min_match ?? 40,
    max_match: body.max_match ?? 200,
    name: body.name || "default",
  };
  if (body.id) {
    await env.DB.prepare(
      "UPDATE profiles SET name=?, role_taxonomy=?, anti_identity=?, hard_reject=?, domain_keywords=?, skills_keywords=?, geography=?, seniority=?, spoken_languages=?, min_match=?, max_match=?, is_default=0 WHERE id=? AND user_id=?",
    ).bind(sets.name, sets.role_taxonomy, sets.anti_identity, sets.hard_reject, sets.domain_keywords, sets.skills_keywords, sets.geography, sets.seniority, sets.spoken_languages, sets.min_match, sets.max_match, body.id, user.id).run();
  } else {
    await env.DB.prepare(
      "INSERT INTO profiles (user_id, name, role_taxonomy, anti_identity, hard_reject, domain_keywords, skills_keywords, geography, seniority, spoken_languages, min_match, max_match) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    ).bind(user.id, sets.name, sets.role_taxonomy, sets.anti_identity, sets.hard_reject, sets.domain_keywords, sets.skills_keywords, sets.geography, sets.seniority, sets.spoken_languages, sets.min_match, sets.max_match).run();
  }
  return json({ ok: true });
}

async function handleJobs(req: Request, env: Env, githubId: number): Promise<Response> {
  const u = new URL(req.url);
  const min = parseInt(u.searchParams.get("min") || "40", 10) || 40;
  const max = parseInt(u.searchParams.get("max") || "200", 10) || 200;
  const limit = Math.min(parseInt(u.searchParams.get("limit") || "200", 10) || 200, 500);
  const profileId = u.searchParams.get("profile_id");

  const user = await env.DB.prepare("SELECT id FROM users WHERE github_id = ?").bind(githubId).first<{ id: number }>();
  if (!user) return json({ error: "user not found" }, 401);

  const profileRow = profileId
    ? await env.DB.prepare(
        "SELECT * FROM profiles WHERE id = ? AND user_id = ?",
      ).bind(profileId, user.id).first<{ role_taxonomy: string; anti_identity: string; hard_reject: string; domain_keywords: string; skills_keywords: string; geography: string; seniority: string; spoken_languages: string; min_match: number; max_match: number; is_default: number }>()
    : await env.DB.prepare(
        "SELECT * FROM profiles WHERE user_id = ? ORDER BY is_default DESC, id LIMIT 1",
      ).bind(user.id).first<{ role_taxonomy: string; anti_identity: string; hard_reject: string; domain_keywords: string; skills_keywords: string; geography: string; seniority: string; spoken_languages: string; min_match: number; max_match: number; is_default: number }>();
  if (!profileRow) return json({ error: "no profile" }, 400);

  const effectiveMin = Math.max(min, profileRow.min_match);
  const effectiveMax = Math.min(max, profileRow.max_match);

  const cols =
    `id, title, company, location, source, url, posted, salary_raw, salary_min_eur, salary_max_eur,
     lang, lang_req, years_min, eng_title, hard_block, hard_tech, title_lower, text_lower, match, role_family, why`;

  if (profileRow.is_default) {
    const rows = await env.DB.prepare(
      `SELECT ${cols} FROM jobs
       WHERE hard_block = 0 AND hard_tech = 0 AND match BETWEEN ? AND ?
       ORDER BY match DESC, posted DESC LIMIT ?`,
    ).bind(effectiveMin, effectiveMax, limit).all();
    const jobs = (rows.results || []).map((r) => {
      const { role_family, ...rest } = r;
      return { ...rest, roleFamily: role_family, why: r.why || "" };
    });
    return json({ count: jobs.length, jobs });
  }

  const profile: Profile = {
    role_taxonomy: JSON.parse(profileRow.role_taxonomy),
    anti_identity: JSON.parse(profileRow.anti_identity || '{"reject_title_patterns":[]}'),
    hard_reject: JSON.parse(profileRow.hard_reject || '{"languages_forbidden":[],"languages_spoken":["english"],"max_years_experience":6,"restricted_locations":[],"forbidden_certs":[],"production_patterns":[],"established_network_patterns":[]}'),
    domain_keywords: JSON.parse(profileRow.domain_keywords),
    skills_keywords: JSON.parse(profileRow.skills_keywords),
    geography: JSON.parse(profileRow.geography),
    seniority: JSON.parse(profileRow.seniority),
    spoken_languages: JSON.parse(profileRow.spoken_languages || '["english"]'),
    min_match: profileRow.min_match,
    max_match: profileRow.max_match,
  };

  const rows = await env.DB.prepare(
    `SELECT ${cols} FROM jobs WHERE hard_block = 0 AND hard_tech = 0`,
  ).all<JobRow>();

  const results = (rows.results || [])
    .map((j) => scoreJob(j, profile))
    .filter((s) => s.match >= effectiveMin && s.match <= effectiveMax)
    .sort((a, b) => b.match - a.match)
    .slice(0, limit);

  return json({ count: results.length, jobs: results });
}

async function handleStats(env: Env): Promise<Response> {
  const total = await env.DB.prepare("SELECT count(*) as c FROM jobs").first<{ c: number }>();
  const over40 = await env.DB.prepare("SELECT count(*) as c FROM jobs WHERE match >= 40").first<{ c: number }>();
  const over60 = await env.DB.prepare("SELECT count(*) as c FROM jobs WHERE match >= 60").first<{ c: number }>();
  const over80 = await env.DB.prepare("SELECT count(*) as c FROM jobs WHERE match >= 80").first<{ c: number }>();
  const avgMatch = await env.DB.prepare("SELECT round(avg(match)) as a FROM jobs WHERE match >= 40").first<{ a: number }>();
  const byRole = await env.DB.prepare("SELECT role_family, count(*) as c, round(avg(match)) as avg_m FROM jobs WHERE match >= 40 GROUP BY role_family ORDER BY c DESC").all();
  const byCountry = await env.DB.prepare(
    `SELECT CASE
       WHEN location LIKE '%Netherlands%' OR location LIKE '%Amsterdam%' THEN 'Netherlands'
       WHEN location LIKE '%Ireland%' OR location LIKE '%Dublin%' THEN 'Ireland'
       WHEN location LIKE '%United Kingdom%' OR location LIKE '%London%' THEN 'UK'
       WHEN location LIKE '%Germany%' OR location LIKE '%Berlin%' OR location LIKE '%Munich%' THEN 'Germany'
       WHEN location LIKE '%United Arab%' OR location LIKE '%Dubai%' OR location LIKE '%Abu Dhabi%' THEN 'UAE'
       WHEN location LIKE '%Switzerland%' OR location LIKE '%Zurich%' THEN 'Switzerland'
       WHEN location LIKE '%Mexico%' OR location LIKE '%CDMX%' THEN 'Mexico'
       WHEN location LIKE '%Singapore%' THEN 'Singapore'
       WHEN location LIKE '%Sweden%' OR location LIKE '%Stockholm%' THEN 'Sweden'
       WHEN location LIKE '%Remote%' THEN 'Remote'
       ELSE 'Other'
     END as country, count(*) as c, round(avg(match)) as avg_m
     FROM jobs WHERE match >= 40 GROUP BY country ORDER BY c DESC`
  ).all();
  const topJobs = await env.DB.prepare("SELECT id, title, company, location, match, role_family, why, url FROM jobs WHERE match >= 60 ORDER BY match DESC LIMIT 10").all();
  return json({
    total: total?.c || 0,
    over40: over40?.c || 0,
    over60: over60?.c || 0,
    over80: over80?.c || 0,
    avgMatch: avgMatch?.a || 0,
    byRole: byRole.results,
    byCountry: byCountry.results,
    topJobs: topJobs.results,
  });
}

// ---------------------------------------------------------------- Admin

function isAdmin(req: Request, env: Env): boolean {
  const auth = req.headers.get("Authorization") || "";
  const key = auth.replace(/^Bearer\s+/i, "").trim();
  return key.length > 0 && key === env.ADMIN_KEY;
}

async function handleAdminUsers(req: Request, env: Env): Promise<Response> {
  if (!isAdmin(req, env)) return json({ error: "unauthorized" }, 403);

  if (req.method === "GET") {
    const rows = await env.DB.prepare(
      "SELECT id, github_id, login, name, avatar_url, created_at FROM users ORDER BY id",
    ).all();
    return json({ users: rows.results });
  }

  if (req.method === "POST") {
    const body = (await req.json()) as { github_id: number; login: string };
    if (!body.github_id || !body.login) return json({ error: "github_id and login required" }, 400);
    const existing = await env.DB.prepare("SELECT id FROM users WHERE github_id = ?").bind(body.github_id).first<{ id: number }>();
    if (existing) return json({ error: "user already exists", id: existing.id }, 409);
    const res = await env.DB.prepare("INSERT INTO users (github_id, login) VALUES (?, ?)").bind(body.github_id, body.login).run();
    const userId = Number(res.meta.last_row_id);
    const def = await defaultProfile();
    await env.DB.prepare(
      "INSERT INTO profiles (user_id, name, role_taxonomy, anti_identity, hard_reject, domain_keywords, skills_keywords, geography, seniority, min_match, max_match, is_default) VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
    ).bind(userId, JSON.stringify(def.role_taxonomy), JSON.stringify(def.anti_identity),
      JSON.stringify(def.hard_reject), JSON.stringify(def.domain_keywords),
      JSON.stringify(def.skills_keywords), JSON.stringify(def.geography),
      JSON.stringify(def.seniority), def.min_match, def.max_match).run();
    return json({ ok: true, id: userId, github_id: body.github_id, login: body.login });
  }

  return json({ error: "method not allowed" }, 405);
}

async function handleAdminDeleteUser(req: Request, env: Env, userId: string): Promise<Response> {
  if (!isAdmin(req, env)) return json({ error: "unauthorized" }, 403);
  const uid = parseInt(userId, 10);
  if (isNaN(uid)) return json({ error: "invalid user id" }, 400);
  await env.DB.prepare("DELETE FROM profiles WHERE user_id = ?").bind(uid).run();
  await env.DB.prepare("DELETE FROM users WHERE id = ?").bind(uid).run();
  return json({ ok: true, deleted: uid });
}

async function handleAdminStats(env: Env): Promise<Response> {
  const stats = await env.DB.prepare(
    "SELECT " +
    "(SELECT count(*) FROM users) as total_users, " +
    "(SELECT count(*) FROM profiles) as total_profiles, " +
    "(SELECT count(*) FROM jobs) as total_jobs, " +
    "(SELECT count(*) FROM jobs WHERE match >= 40) as jobs_over40, " +
    "(SELECT max(match) FROM jobs) as max_match",
  ).first();
  return json(stats);
}

// ---------------------------------------------------------------- Router

async function handleRequest(req: Request, env: Env): Promise<Response> {
  const u = new URL(req.url);
  const origin = req.headers.get("Origin");
  const githubId = await readSession(readCookie(req), env.SESSION_SECRET);

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(origin) });

  // Public routes
  if (u.pathname === "/") return html(FRONTEND);
  if (u.pathname === "/api/health") return json({ ok: true, name: "cazador-api", you: githubId }, 200, origin);
  if (u.pathname === "/api/stats") return handleStats(env);
  if (u.pathname === "/auth/github") return handleAuthGithub(env);
  if (u.pathname === "/auth/callback") return handleAuthCallback(req, env, origin);
  if (u.pathname === "/auth/logout" && req.method === "POST") return logoutCookie(origin);

  // Admin routes (check before auth so admin key works even without session)
  if (u.pathname === "/api/admin/users") return handleAdminUsers(req, env);
  if (u.pathname === "/api/admin/stats") return handleAdminStats(env);
  const delMatch = u.pathname.match(/^\/api\/admin\/users\/(\d+)$/);
  if (delMatch && req.method === "DELETE") return handleAdminDeleteUser(req, env, delMatch[1]);

  // Auth required
  if (!githubId) return json({ error: "no session" }, 401, origin);

  if (u.pathname === "/api/me") return handleMe(env, githubId);
  if (u.pathname === "/api/profile" && req.method === "POST") return handleProfile(req, env, githubId);
  if (u.pathname === "/api/jobs") return handleJobs(req, env, githubId);

  return json({ error: "not found" }, 404, origin);
}

export default {
  fetch: (req: Request, env: Env): Promise<Response> => handleRequest(req, env),
};
