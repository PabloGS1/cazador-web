// Port 1:1 de matcher.score() (matcher.py) a TypeScript para el Worker.
// Fórmula nueva: 100 × role_weight × geo_weight × (0.5 + 0.5 × domain_overlap) × seniority_fit
// Hard rejects → score = 0 antes de la fórmula.

export interface Profile {
  role_taxonomy: {
    tier_a: { weight: number; label: string; titles: string[] };
    tier_b: { weight: number; label: string; titles: string[] };
    tier_c: { weight: number; label: string; titles: string[] };
  };
  anti_identity: { reject_title_patterns: string[] };
  hard_reject: {
    languages_forbidden: string[];
    languages_spoken: string[];
    max_years_experience: number;
    restricted_locations: string[];
    forbidden_certs: string[];
    production_patterns: string[];
    established_network_patterns: string[];
  };
  geography: { weight: number; scoring: Record<string, number> };
  domain_keywords: { weight: number; keywords: string[][] };
  skills_keywords: { weight: number; keywords: string[] };
  seniority: {
    bonus: string[];
    penalty: string[];
    director_penalty: number;
    junior_penalty: number;
  };
  spoken_languages: string[];
  min_match: number;
  max_match: number;
}

export interface JobRow {
  id: string;
  title: string;
  company: string;
  location: string;
  source: string;
  url: string;
  posted: string;
  salary_raw: string;
  salary_min_eur: number | null;
  salary_max_eur: number | null;
  lang: string;
  lang_req: string;
  years_min: number;
  eng_title: number;
  hard_block: number;
  hard_tech: number;
  title_lower: string;
  text_lower: string;
}

export interface Scored {
  id: string;
  match: number;
  roleFamily: string;
  why: string;
}

function matchAny(text: string, kws: string[]): boolean {
  for (const k of kws) {
    if (text.includes(k)) return true;
  }
  return false;
}

function scoreRole(title: string, _text: string, profile: Profile): [number, string] {
  const tax = profile.role_taxonomy;
  // Tier A first
  for (const t of tax.tier_a.titles) {
    if (title.includes(t)) return [tax.tier_a.weight, tax.tier_a.label];
  }
  // Tier B
  for (const t of tax.tier_b.titles) {
    if (title.includes(t)) return [tax.tier_b.weight, tax.tier_b.label];
  }
  // Tier C
  for (const t of tax.tier_c.titles) {
    if (title.includes(t)) return [tax.tier_c.weight, tax.tier_c.label];
  }
  return [0, ""];
}

function domainOverlap(text: string, profile: Profile): number {
  const groups = profile.domain_keywords.keywords;
  if (!groups.length) return 0;
  let hits = 0;
  for (const group of groups) {
    if (matchAny(text, group)) hits++;
  }
  return hits / groups.length;
}

function scoreLocation(job: JobRow, profile: Profile): number {
  const blob = (job.location || "").toLowerCase() + " " + (job.source || "").toLowerCase();
  const geo = profile.geography.scoring;
  let best = 0.3; // default for remote/unmatched
  for (const [kw, w] of Object.entries(geo)) {
    if (blob.includes(kw.toLowerCase())) best = Math.max(best, w);
  }
  return best;
}

function seniorityFit(text: string, profile: Profile): number {
  const cfg = profile.seniority;
  // Check junior/intern first → 0.0 or director_penalty
  for (const k of cfg.penalty) {
    if (text.includes(k)) {
      if (k === "director" || k === "vp" || k === "vice president") {
        return cfg.director_penalty;
      }
      return cfg.junior_penalty;
    }
  }
  // Check senior/lead/manager → 1.0
  for (const k of cfg.bonus) {
    if (text.includes(k)) return 1.0;
  }
  return 1.0;
}

function hardRejects(job: JobRow, profile: Profile): [boolean, string] {
  const title = job.title_lower || "";
  const text = job.text_lower || "";
  const hr = profile.hard_reject;
  const ai = profile.anti_identity;

  // 1. Anti-identity: reject title patterns
  for (const pat of ai.reject_title_patterns) {
    if (title.includes(pat)) return [true, `anti-identity: ${pat}`];
  }

  // 2. Language required that user doesn't speak
  if (job.lang_req) {
    const userLangs = new Set(hr.languages_spoken);
    const reqLangs = new Set(job.lang_req.split(",").map(l => l.trim()).filter(Boolean));
    const hasLang = [...reqLangs].some(l => userLangs.has(l));
    if (!hasLang) return [true, `lang required: ${job.lang_req}`];
  }

  // 3. Years experience > max
  if (job.years_min > hr.max_years_experience) {
    return [true, `years_min ${job.years_min} > ${hr.max_years_experience}`];
  }

  // 4. Restricted location
  for (const pat of hr.restricted_locations) {
    if (text.includes(pat)) return [true, `restricted location: ${pat}`];
  }

  // 5. Forbidden certifications
  for (const cert of hr.forbidden_certs) {
    if (text.includes(cert)) return [true, `forbidden cert: ${cert}`];
  }

  // 6. Hands-on production ownership
  for (const pat of hr.production_patterns) {
    if (text.includes(pat)) return [true, `production ownership: ${pat}`];
  }

  // 7. Established network in specific market
  for (const pat of hr.established_network_patterns) {
    if (text.includes(pat)) return [true, `network required: ${pat}`];
  }

  // 8. Language not english
  if (job.lang !== "en") return [true, `not english: ${job.lang}`];

  return [false, ""];
}

export function scoreJob(job: JobRow, profile: Profile): Scored {
  const title = job.title_lower || "";
  const text = job.text_lower || "";

  // --- Hard rejects → 0 ---
  const [rejected, rejReason] = hardRejects(job, profile);
  if (rejected) return { id: job.id, match: 0, roleFamily: "REJECTED", why: rejReason };

  // --- Role taxonomy filter ---
  const [roleW, roleLabel] = scoreRole(title, text, profile);
  if (roleW === 0) return { id: job.id, match: 0, roleFamily: "no role match", why: "title not in tier A/B/C" };

  // --- Formula ---
  const geoW = scoreLocation(job, profile);
  const domainOv = domainOverlap(text, profile);
  const domainMod = 0.5 + 0.5 * domainOv;
  const senFit = seniorityFit(text, profile);

  let match = Math.round(100 * roleW * geoW * domainMod * senFit);
  match = Math.max(0, Math.min(90, match));

  // --- Build reasons ---
  const reasons: string[] = [];
  reasons.push(roleLabel);
  if (geoW < 0.3) reasons.push(`geo ${geoW.toFixed(2)}`);
  else if (geoW >= 0.8) reasons.push(`geo ${geoW.toFixed(2)}`);
  if (domainOv > 0) reasons.push(`domain ${Math.round(domainOv * 100)}%`);
  if (senFit < 1.0) reasons.push(`seniority ×${senFit}`);

  return { id: job.id, match, roleFamily: roleLabel, why: reasons.join("; ") };
}
