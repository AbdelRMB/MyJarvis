/**
 * Les IA utilisables comme cerveau sur le téléphone : le même catalogue que wesley/fournisseurs.py (identifiant,
 * adresse, nom de la clé dans le coffre du compte, modèle par défaut). La clé API saisie sur un ordinateur sert
 * donc aussi au téléphone (coffre chiffré du compte), et inversement.
 *
 * Les IA locales (Ollama, LM Studio) tournent sur l'ordinateur : le téléphone ne peut pas les joindre depuis une
 * page HTTPS. Il passe alors par le relais (l'ordinateur traite la demande), sauf si une adresse HTTPS d'Ollama
 * est donnée dans les réglages du téléphone.
 */
export type Fournisseur = { id: string; nom: string; url: string; env: string; defaut: string; detail: string };

export const CLAUDE_MODELES: Record<string, string> = {
  "claude-sonnet-5-5": "Sonnet 5.5 — intelligent et rapide (recommandé)",
  "claude-haiku-5-5": "Haiku 5.5 — très économique",
  "claude-opus-5-5": "Opus 5.5 — le plus intelligent, ~2x plus cher",
};
export const CLAUDE_DEFAUT = "claude-sonnet-5-5";

export const FOURNISSEURS: Fournisseur[] = [
  { id: "openai", nom: "OpenAI (GPT)", url: "https://api.openai.com/v1", env: "OPENAI_API_KEY", defaut: "gpt-4o", detail: "platform.openai.com › API keys" },
  {
    id: "gemini",
    nom: "Google Gemini",
    url: "https://generativelanguage.googleapis.com/v1beta/openai",
    env: "GEMINI_API_KEY",
    defaut: "gemini-2.5-flash",
    detail: "aistudio.google.com › Get API key (gratuit avec limites)",
  },
  { id: "mistral", nom: "Mistral AI", url: "https://api.mistral.ai/v1", env: "MISTRAL_API_KEY", defaut: "mistral-large-latest", detail: "console.mistral.ai › API Keys" },
  { id: "deepseek", nom: "DeepSeek", url: "https://api.deepseek.com", env: "DEEPSEEK_API_KEY", defaut: "deepseek-chat", detail: "platform.deepseek.com › API keys" },
  { id: "xai", nom: "Grok (xAI)", url: "https://api.x.ai/v1", env: "XAI_API_KEY", defaut: "grok-4", detail: "console.x.ai › API Keys" },
  { id: "openrouter", nom: "OpenRouter", url: "https://openrouter.ai/api/v1", env: "OPENROUTER_API_KEY", defaut: "openai/gpt-4o", detail: "openrouter.ai › Keys" },
  { id: "groq", nom: "Groq", url: "https://api.groq.com/openai/v1", env: "GROQ_API_KEY", defaut: "llama-3.3-70b-versatile", detail: "console.groq.com › API Keys (gratuit)" },
  { id: "cerebras", nom: "Cerebras", url: "https://api.cerebras.ai/v1", env: "CEREBRAS_API_KEY", defaut: "llama-3.3-70b", detail: "cloud.cerebras.ai › API Keys (gratuit)" },
  { id: "together", nom: "Together AI", url: "https://api.together.xyz/v1", env: "TOGETHER_API_KEY", defaut: "meta-llama/Llama-3.3-70B-Instruct-Turbo", detail: "api.together.ai" },
  {
    id: "fireworks",
    nom: "Fireworks AI",
    url: "https://api.fireworks.ai/inference/v1",
    env: "FIREWORKS_API_KEY",
    defaut: "accounts/fireworks/models/llama-v3p3-70b-instruct",
    detail: "fireworks.ai › API Keys",
  },
  { id: "moonshot", nom: "Kimi (Moonshot)", url: "https://api.moonshot.ai/v1", env: "MOONSHOT_API_KEY", defaut: "kimi-k2-0905-preview", detail: "platform.moonshot.ai" },
  { id: "qwen", nom: "Qwen (Alibaba)", url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", env: "DASHSCOPE_API_KEY", defaut: "qwen-plus", detail: "Alibaba Model Studio" },
  { id: "cohere", nom: "Cohere", url: "https://api.cohere.ai/compatibility/v1", env: "CO_API_KEY", defaut: "command-a-03-2025", detail: "dashboard.cohere.com" },
  { id: "huggingface", nom: "Hugging Face", url: "https://router.huggingface.co/v1", env: "HF_TOKEN", defaut: "openai/gpt-oss-120b", detail: "huggingface.co › Access Tokens" },
  { id: "perso", nom: "Autre (compatible OpenAI)", url: "perso", env: "PERSO_API_KEY", defaut: "", detail: "adresse HTTPS de ton service" },
];

export const PAR_ID: Record<string, Fournisseur> = Object.fromEntries(FOURNISSEURS.map((f) => [f.id, f]));
export const LOCAUX = ["ollama", "lmstudio"];

/** Tous les choix de cerveau proposés sur le téléphone. */
export const CHOIX_CERVEAUX: { id: string; nom: string }[] = [
  { id: "claude", nom: "Claude (Anthropic)" },
  ...FOURNISSEURS.map((f) => ({ id: f.id, nom: f.nom })),
  { id: "ollama", nom: "Ollama (sur ton ordinateur)" },
  { id: "relais", nom: "Mon ordinateur traite tout (relais)" },
];
