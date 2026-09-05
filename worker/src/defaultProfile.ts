// GENERADO por make_default_profile.py desde profile.yaml - no editar a mano.
export interface DefaultProfile {
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

export const DEFAULT_PROFILE: DefaultProfile = {
  "role_taxonomy": {
    "tier_a": {
      "weight": 1.0,
      "label": "Target directo",
      "titles": [
        "account executive",
        "enterprise account executive",
        "strategic account executive",
        "account director",
        "account manager",
        "key account manager",
        "kam",
        "enterprise account manager",
        "business development",
        "business development manager",
        "business development director",
        "business development lead",
        "partnership",
        "partnerships",
        "partner manager",
        "alliances manager",
        "alliance manager",
        "channel manager",
        "solutions consultant",
        "business value consultant",
        "value engineer",
        "sales engineer",
        "pre-sales",
        "presales",
        "solutions engineer",
        "solution engineer",
        "solutions architect",
        "pre-sales consultant",
        "presales consultant",
        "technical account manager",
        "enterprise sales manager",
        "public sector account manager",
        "government account executive",
        "public sector account executive",
        "bid manager",
        "proposal manager",
        "capture manager",
        "deal manager"
      ]
    },
    "tier_b": {
      "weight": 0.6,
      "label": "Encaje parcial",
      "titles": [
        "commercial finance manager",
        "commercial manager",
        "deal desk",
        "customer success manager",
        "sales operations",
        "revenue operations",
        "go-to-market",
        "gtm manager",
        "market development manager"
      ]
    },
    "tier_c": {
      "weight": 0.4,
      "label": "Solo data centre / AI infra",
      "titles": [
        "development manager",
        "origination manager",
        "investment analyst",
        "commercial analyst"
      ]
    }
  },
  "anti_identity": {
    "reject_title_patterns": [
      "machine learning engineer",
      "ml engineer",
      "mlops",
      "platform engineer",
      "data engineer",
      "analytics engineer",
      "data scientist",
      "software engineer",
      "devops",
      "sre",
      "site reliability",
      "cloud engineer",
      "security engineer",
      "ai architect",
      "implementation consultant",
      "technical support",
      "product manager",
      "product marketing",
      "data analyst",
      "research scientist",
      "research engineer",
      "applied scientist",
      "sdr",
      "bdr",
      "inside sales",
      "lead generation",
      "sales development"
    ]
  },
  "hard_reject": {
    "languages_forbidden": [
      "dutch",
      "flemish",
      "danish",
      "norwegian",
      "swedish",
      "finnish",
      "italian",
      "portuguese",
      "mandarin",
      "cantonese",
      "japanese",
      "korean",
      "thai",
      "indonesian",
      "malay",
      "vietnamese",
      "turkish",
      "polish",
      "czech",
      "hungarian",
      "greek",
      "russian",
      "hindi",
      "tamil"
    ],
    "languages_spoken": [
      "english",
      "spanish",
      "french"
    ],
    "max_years_experience": 8,
    "restricted_locations": [
      "us only",
      "united states only",
      "canada only",
      "latam only",
      "india only",
      "usa only"
    ],
    "forbidden_certs": [
      "aws solutions architect professional",
      "aws sa pro",
      "cissp",
      "comptia",
      "ccnp",
      "ccie"
    ],
    "production_patterns": [
      "on-call",
      "on call",
      "incident response",
      "code review",
      "pull request"
    ],
    "established_network_patterns": [
      "well-connected in",
      "established network in",
      "strong network in",
      "deep connections in",
      "existing relationships in"
    ]
  },
  "geography": {
    "weight": 30,
    "scoring": {
      "united arab emirates": 1.0,
      "uae": 1.0,
      "abu dhabi": 1.0,
      "dubai": 1.0,
      "netherlands": 1.0,
      "amsterdam": 1.0,
      "utrecht": 1.0,
      "rotterdam": 1.0,
      "eindhoven": 1.0,
      "the hague": 1.0,
      "ireland": 0.9,
      "dublin": 0.9,
      "united kingdom": 0.85,
      "uk": 0.85,
      "london": 0.85,
      "england": 0.85,
      "germany": 0.8,
      "munich": 0.8,
      "berlin": 0.8,
      "frankfurt": 0.8,
      "mexico": 0.8,
      "mexico city": 0.8,
      "cdmx": 0.8,
      "guadalajara": 0.8,
      "monterrey": 0.8,
      "switzerland": 0.7,
      "zurich": 0.7,
      "zug": 0.7,
      "basel": 0.7,
      "geneva": 0.7,
      "sweden": 0.65,
      "stockholm": 0.65,
      "singapore": 0.6,
      "saudi arabia": 0.55,
      "saudi": 0.55,
      "qatar": 0.55,
      "riyadh": 0.55,
      "malaysia": 0.4,
      "denmark": 0.4,
      "norway": 0.4,
      "poland": 0.4,
      "portugal": 0.4,
      "copenhagen": 0.4,
      "oslo": 0.4,
      "warsaw": 0.4,
      "remote - emea": 0.3,
      "remote": 0.3,
      "emea": 0.3,
      "europe": 0.3,
      "spain": 0.0,
      "madrid": 0.0,
      "barcelona": 0.0,
      "us only": 0.0,
      "united states": 0.0,
      "usa": 0.0
    }
  },
  "domain_keywords": {
    "weight": 1,
    "keywords": [
      [
        "ai sales",
        "data sales",
        "ai infrastructure",
        "data platform",
        "genai",
        "generative ai",
        "rag",
        "ai agents",
        "agentic",
        "llm",
        "machine learning",
        "ai factory",
        "ai factories"
      ],
      [
        "databricks",
        "snowflake",
        "denodo",
        "nvidia",
        "dell",
        "hpe",
        "fujitsu",
        "microsoft",
        "ibm",
        "data lake",
        "data lakehouse",
        "data space",
        "data virtualisation",
        "data virtualization",
        "data migration"
      ],
      [
        "data center",
        "datacenter",
        "data centre",
        "gpu compute",
        "hpc",
        "compute",
        "ai infrastructure",
        "ai operations",
        "semiconductor",
        "energy",
        "power",
        "colocation",
        "hyperscale"
      ],
      [
        "cloud",
        "saas",
        "paas",
        "iaas",
        "aws",
        "azure",
        "gcp",
        "kubernetes"
      ],
      [
        "iot",
        "smart city",
        "smart cities",
        "connectivity",
        "telecom"
      ],
      [
        "public sector",
        "government",
        "public administration",
        "procurement",
        "public procurement",
        "tender",
        "tenders",
        "citizen",
        "eu ai act",
        "data governance",
        "data lineage",
        "ai governance"
      ],
      [
        "european commission",
        "european union",
        "eu institutions",
        "trade policy",
        "economics",
        "economy",
        "single market",
        "commercial diplomacy"
      ],
      [
        "openai",
        "anthropic",
        "gemini",
        "gpt",
        "copilot",
        "chatbot",
        "virtual assistant",
        "automation",
        "rpa"
      ]
    ]
  },
  "skills_keywords": {
    "weight": 1,
    "keywords": [
      "salesforce",
      "power bi",
      "sql",
      "rfp",
      "rfi",
      "proof of concept",
      "poc",
      "presales",
      "pre-sales",
      "pipeline",
      "kpi",
      "stakeholder",
      "consultative",
      "negotiation",
      "contract",
      "business case",
      "go-to-market",
      "gtm",
      "demo",
      "tender",
      "procurement",
      "solutions architecture",
      "sales cycle",
      "deal",
      "nvidia",
      "cfa",
      "mba",
      "denodo",
      "stratio",
      "mlops",
      "data governance",
      "eu ai act",
      "reference architecture",
      "semiconductor",
      "energy"
    ]
  },
  "seniority": {
    "bonus": [
      "senior",
      "lead",
      "manager",
      "principal",
      "head"
    ],
    "penalty": [
      "intern",
      "internship",
      "graduate",
      "working student",
      "junior",
      "trainee",
      "practice",
      "director",
      "vp",
      "vice president"
    ],
    "director_penalty": 0.3,
    "junior_penalty": 0.0
  },
  "spoken_languages": [
    "english",
    "spanish",
    "french"
  ],
  "min_match": 40,
  "max_match": 200
};
