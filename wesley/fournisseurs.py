"""Catalogue des IA qui peuvent servir de cerveau à Wesley.

Claude (claude.py) et Ollama (agent.py) ont leur propre code. Toutes les autres parlent le format de l'API OpenAI
(« compatible OpenAI ») : un seul cerveau (openai_cerveau.py) les pilote, seuls changent l'adresse, la clé et le modèle.

Chaque fournisseur :
- id       : valeur de CONFIG["cerveau"] ; le modèle choisi est dans CONFIG["<id>_modele"]
- url      : adresse de l'API (None = OpenAI ; « perso » = CONFIG["perso_url"])
- env      : nom de la clé API dans .env et dans le coffre chiffré du compte (None = pas de clé)
- cle_ou   : où créer la clé ; prefixe : début attendu de la clé (vérification légère)
- preferes : motifs cherchés dans les noms de modèles, par ordre de préférence (le plus récent d'abord)
- exclus   : modèles qui ne savent pas discuter avec des outils (images, audio, embeddings…)
- defaut   : modèle utilisé si la liste des modèles est indisponible
- local    : tourne sur l'ordinateur (gratuit, privé)

Ce module ne dépend de rien d'autre dans Wesley (config.py l'importe).
"""

_EXCLUS = ("embed", "audio", "realtime", "tts", "transcribe", "whisper", "image", "imagen", "imagine", "dall",
           "moderation", "guard", "rerank", "ocr", "search", "veo", "lyria", "aqa", "live")

FOURNISSEURS: list[dict] = [
    {"id": "openai", "nom": "OpenAI (GPT)", "url": None, "env": "OPENAI_API_KEY", "prefixe": "sk-",
     "cle_ou": "platform.openai.com › API keys. L'abonnement ChatGPT Plus n'inclut pas de crédit API.",
     "detail": "GPT-5 et les autres modèles d'OpenAI. Payant, données envoyées à OpenAI.",
     "preferes": ["gpt-5", "gpt-4.1", "gpt-4o"], "defaut": "gpt-4o", "filtre": ("gpt-", "o1", "o3", "o4", "o5")},
    {"id": "gemini", "nom": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "env": "GEMINI_API_KEY", "prefixe": "",
     "cle_ou": "aistudio.google.com › Get API key. Offre gratuite avec des limites par minute et par jour.",
     "detail": "Gemini Pro et Flash de Google. Offre gratuite, données envoyées à Google.",
     "preferes": ["gemini-3-pro", "gemini-2.5-pro", "gemini-3-flash", "gemini-2.5-flash", "pro", "flash"],
     "defaut": "gemini-2.5-flash", "filtre": ("gemini",)},
    {"id": "mistral", "nom": "Mistral AI", "url": "https://api.mistral.ai/v1", "env": "MISTRAL_API_KEY", "prefixe": "",
     "cle_ou": "console.mistral.ai › API Keys. Offre gratuite « Experiment » pour essayer.",
     "detail": "L'IA française. Offre gratuite pour essayer, données hébergées en Europe.",
     "preferes": ["mistral-large-latest", "mistral-medium-latest", "mistral-large", "mistral-medium", "mistral-small-latest"],
     "defaut": "mistral-large-latest", "filtre": ("mistral", "magistral", "codestral", "devstral", "ministral", "pixtral")},
    {"id": "deepseek", "nom": "DeepSeek", "url": "https://api.deepseek.com", "env": "DEEPSEEK_API_KEY", "prefixe": "sk-",
     "cle_ou": "platform.deepseek.com › API keys. Très bon marché (recharge de quelques euros).",
     "detail": "Très bon rapport qualité-prix. Payant, données envoyées à DeepSeek (Chine).",
     "preferes": ["deepseek-chat", "deepseek-reasoner"], "defaut": "deepseek-chat", "filtre": ("deepseek",)},
    {"id": "xai", "nom": "Grok (xAI)", "url": "https://api.x.ai/v1", "env": "XAI_API_KEY", "prefixe": "xai-",
     "cle_ou": "console.x.ai › API Keys.",
     "detail": "Les modèles Grok d'Elon Musk. Payant, données envoyées à xAI.",
     "preferes": ["grok-4", "grok-3"], "defaut": "grok-4", "filtre": ("grok",)},
    {"id": "openrouter", "nom": "OpenRouter", "url": "https://openrouter.ai/api/v1", "env": "OPENROUTER_API_KEY",
     "prefixe": "sk-or-", "cle_ou": "openrouter.ai › Keys. Une seule clé et un seul crédit pour des centaines de modèles.",
     "detail": "Une clé pour toutes les IA (Claude, GPT, Gemini, Llama, Qwen…), dont des modèles gratuits.",
     "preferes": ["anthropic/claude-sonnet", "openai/gpt-5", "google/gemini-2.5-pro"], "defaut": "openai/gpt-4o"},
    {"id": "groq", "nom": "Groq", "url": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY", "prefixe": "gsk_",
     "cle_ou": "console.groq.com › API Keys. Gratuit avec des limites.",
     "detail": "Réponses ultra rapides (Llama, Kimi, GPT-OSS…). Offre gratuite.",
     "preferes": ["kimi-k2", "gpt-oss-120b", "llama-4-maverick", "llama-3.3-70b"], "defaut": "llama-3.3-70b-versatile"},
    {"id": "cerebras", "nom": "Cerebras", "url": "https://api.cerebras.ai/v1", "env": "CEREBRAS_API_KEY", "prefixe": "csk-",
     "cle_ou": "cloud.cerebras.ai › API Keys. Gratuit avec des limites.",
     "detail": "Parmi les plus rapides au monde (Llama, Qwen, GPT-OSS). Offre gratuite.",
     "preferes": ["gpt-oss-120b", "qwen-3-235b", "llama-4-maverick", "llama-3.3-70b"], "defaut": "llama-3.3-70b"},
    {"id": "together", "nom": "Together AI", "url": "https://api.together.xyz/v1", "env": "TOGETHER_API_KEY", "prefixe": "",
     "cle_ou": "api.together.ai › Settings › API Keys.",
     "detail": "Les grands modèles open source (Llama, Qwen, DeepSeek…) dans le cloud.",
     "preferes": ["Qwen3-235B", "DeepSeek-V3", "Llama-4-Maverick", "Llama-3.3-70B"],
     "defaut": "meta-llama/Llama-3.3-70B-Instruct-Turbo"},
    {"id": "fireworks", "nom": "Fireworks AI", "url": "https://api.fireworks.ai/inference/v1", "env": "FIREWORKS_API_KEY",
     "prefixe": "fw_", "cle_ou": "fireworks.ai › Account › API Keys.",
     "detail": "Modèles open source rapides (Kimi, Qwen, DeepSeek, Llama).",
     "preferes": ["kimi-k2", "qwen3-235b", "deepseek-v3", "llama-v3p3-70b"],
     "defaut": "accounts/fireworks/models/llama-v3p3-70b-instruct"},
    {"id": "moonshot", "nom": "Kimi (Moonshot)", "url": "https://api.moonshot.ai/v1", "env": "MOONSHOT_API_KEY",
     "prefixe": "sk-", "cle_ou": "platform.moonshot.ai › API Keys.",
     "detail": "Kimi K2, très bon pour les longues tâches avec outils.",
     "preferes": ["kimi-k2", "kimi-latest", "moonshot-v1-128k"], "defaut": "kimi-k2-0905-preview"},
    {"id": "qwen", "nom": "Qwen (Alibaba)", "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
     "env": "DASHSCOPE_API_KEY", "prefixe": "sk-", "cle_ou": "Alibaba Cloud Model Studio (international) › API Key.",
     "detail": "Les modèles Qwen d'Alibaba dans le cloud.",
     "preferes": ["qwen3-max", "qwen-max", "qwen-plus"], "defaut": "qwen-plus", "filtre": ("qwen",)},
    {"id": "cohere", "nom": "Cohere", "url": "https://api.cohere.ai/compatibility/v1", "env": "CO_API_KEY", "prefixe": "",
     "cle_ou": "dashboard.cohere.com › API Keys. Clé d'essai gratuite.",
     "detail": "Les modèles Command de Cohere (Canada).",
     "preferes": ["command-a", "command-r-plus"], "defaut": "command-a-03-2025", "filtre": ("command",)},
    {"id": "huggingface", "nom": "Hugging Face", "url": "https://router.huggingface.co/v1", "env": "HF_TOKEN",
     "prefixe": "hf_", "cle_ou": "huggingface.co › Settings › Access Tokens (droit « Inference Providers »).",
     "detail": "Des milliers de modèles open source, avec un petit crédit gratuit chaque mois.",
     "preferes": ["Qwen3-235B", "gpt-oss-120b", "Llama-3.3-70B"], "defaut": "openai/gpt-oss-120b"},
    {"id": "lmstudio", "nom": "LM Studio (local)", "url": "http://localhost:1234/v1", "env": None, "local": True,
     "cle_ou": "lmstudio.ai : télécharge un modèle, puis lance le serveur (onglet Developer › Start Server).",
     "detail": "Gratuit, 100 % privé : n'importe quel modèle de LM Studio. Utilise ta carte graphique.",
     "preferes": ["qwen", "gpt-oss", "llama", "mistral"], "defaut": ""},
    {"id": "perso", "nom": "Autre (compatible OpenAI)", "url": "perso", "env": "PERSO_API_KEY", "prefixe": "",
     "cle_ou": "Clé de ton service, si besoin (laisse vide pour un serveur local).",
     "detail": "N'importe quel service compatible OpenAI : vLLM, Jan, llama.cpp, LocalAI, Azure, Perplexity…",
     "preferes": [], "defaut": ""},
]

PAR_ID = {f["id"]: f for f in FOURNISSEURS}
CLES_MODELES = [f"{f['id']}_modele" for f in FOURNISSEURS]   # « openai_modele », « gemini_modele »…
ENV_CLES = [f["env"] for f in FOURNISSEURS if f.get("env")]


def est_compatible(cerveau) -> bool:
    """Vrai si ce cerveau passe par openai_cerveau.py (tout sauf Claude et Ollama)."""
    return cerveau in PAR_ID


def garder_modele(f: dict, mid: str) -> bool:
    m = mid.lower()
    if any(x in m for x in _EXCLUS):
        return False
    filtre = f.get("filtre")
    if filtre and not any(x in m for x in filtre):
        return False
    return True


def choisir_modele(f: dict, dispo: list[str]) -> str:
    """Le meilleur modèle disponible : premier motif préféré trouvé, version la plus récente d'abord."""
    tries = sorted(dispo, reverse=True)
    for motif in f.get("preferes", []):
        for m in tries:
            if motif.lower() in m.lower():
                return m
    return f.get("defaut") or (tries[0] if tries else "")


def pour_interface() -> list[dict]:
    return [{"id": f["id"], "nom": f["nom"], "detail": f["detail"], "cle_ou": f["cle_ou"],
             "cle": bool(f.get("env")), "local": bool(f.get("local")), "perso": f["url"] == "perso"} for f in FOURNISSEURS]
