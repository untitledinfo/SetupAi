import type { ModelOption } from "./types";

/**
 * Every model below is a prebuilt WebLLM MLC model. They are pulled straight
 * from the public WebLLM model CDN the first time they're used, cached by the
 * browser (Cache Storage), and served from that cache on every run after —
 * no API key, no server, no manual download/clone step.
 */
export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "Llama-3.2-1B-Instruct-q4f16_1-MLC",
    label: "Llama 3.2 · 1B",
    size: "~0.7 GB",
    vram: "Low VRAM",
    tagline: "Fastest replies. Best for low-end / integrated GPUs.",
  },
  {
    id: "Llama-3.2-3B-Instruct-q4f16_1-MLC",
    label: "Llama 3.2 · 3B",
    size: "~1.9 GB",
    vram: "Mid VRAM",
    tagline: "Balanced quality and speed for most machines.",
  },
  {
    id: "Phi-3.5-mini-instruct-q4f16_1-MLC",
    label: "Phi 3.5 Mini",
    size: "~2.2 GB",
    vram: "Mid VRAM",
    tagline: "Strong reasoning and code, compact footprint.",
  },
  {
    id: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
    label: "Qwen 2.5 · 1.5B",
    size: "~1.0 GB",
    vram: "Low VRAM",
    tagline: "Snappy multilingual model, good default pick.",
  },
  {
    id: "gemma-2-2b-it-q4f16_1-MLC",
    label: "Gemma 2 · 2B",
    size: "~1.5 GB",
    vram: "Low-Mid VRAM",
    tagline: "Google's compact instruct model, clean writing style.",
  },
];

export const DEFAULT_MODEL_ID = MODEL_OPTIONS[0].id;

export const DEFAULT_TEMPERATURE = 0.7;
export const DEFAULT_TOP_P = 0.95;

export const DEFAULT_SYSTEM_PROMPT =
  "You are SetupAI, a concise, capable offline assistant. Answer directly, use markdown and code blocks when useful, and say when you're not sure about something.";
