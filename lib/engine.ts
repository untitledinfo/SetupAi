"use client";

import type { InitProgressReport, MLCEngineInterface } from "@mlc-ai/web-llm";
import type { ChatMessage } from "./types";

type ProgressCallback = (report: InitProgressReport) => void;

export interface GenerationOptions {
  temperature: number;
  topP: number;
}

export interface GenerationStats {
  decodeTokensPerSec: number | null;
  prefillTokensPerSec: number | null;
}

let engine: MLCEngineInterface | null = null;
let loadedModelId: string | null = null;
let loadingPromise: Promise<MLCEngineInterface> | null = null;

// Bumped every time a new load starts, so a stale in-flight load for a model
// the user has since switched away from can detect it's obsolete and avoid
// clobbering `engine`/`loadedModelId` when it eventually resolves.
let loadToken = 0;

export function isWebGPUSupported(): boolean {
  if (typeof navigator === "undefined") return false;
  return Boolean((navigator as Navigator & { gpu?: unknown }).gpu);
}

export function getCurrentModelId(): string | null {
  return loadedModelId;
}

/**
 * Lazily loads (or reuses) the WebLLM engine for a given model.
 * Weights are fetched from the WebLLM CDN once and cached by the browser's
 * Cache Storage — every call after the first is fully offline. Safe to call
 * repeatedly, and safe to call again with a different modelId while a
 * previous load is still in flight (the stale load is discarded, not
 * cancelled — WebLLM has no cancel API — but it can no longer win).
 */
export async function ensureEngine(
  modelId: string,
  onProgress: ProgressCallback
): Promise<MLCEngineInterface> {
  if (engine && loadedModelId === modelId) return engine;

  const myToken = ++loadToken;

  const webllm = await import("@mlc-ai/web-llm");

  const created = await webllm.CreateMLCEngine(modelId, {
    initProgressCallback: onProgress,
  });

  if (myToken !== loadToken) {
    // A newer load (different model) started after this one — this result
    // is stale. Release its resources instead of installing it.
    created.unload().catch(() => {});
    throw new Error("Superseded by a newer model selection.");
  }

  engine = created;
  loadedModelId = modelId;
  loadingPromise = null;
  return created;
}

export async function unloadEngine() {
  loadToken++; // invalidate any in-flight load
  const current = engine;
  engine = null;
  loadedModelId = null;
  loadingPromise = null;
  if (current) {
    try {
      await current.unload();
    } catch {
      // best-effort cleanup
    }
  }
}

export async function* streamChatCompletion(
  modelId: string,
  systemPrompt: string,
  history: ChatMessage[],
  options: GenerationOptions,
  onProgress: ProgressCallback,
  onStats?: (stats: GenerationStats) => void
): AsyncGenerator<string, void, unknown> {
  const eng = await ensureEngine(modelId, onProgress);

  const messages = [
    { role: "system" as const, content: systemPrompt },
    ...history.map((m) => ({ role: m.role, content: m.content })),
  ];

  const stream = await eng.chat.completions.create({
    messages,
    stream: true,
    stream_options: { include_usage: true },
    temperature: options.temperature,
    top_p: options.topP,
  });

  for await (const chunk of stream) {
    const delta = chunk.choices?.[0]?.delta?.content;
    if (delta) yield delta;

    const usage = (chunk as { usage?: { extra?: Record<string, number> } }).usage;
    if (usage?.extra && onStats) {
      onStats({
        decodeTokensPerSec: usage.extra.decode_tokens_per_s ?? null,
        prefillTokensPerSec: usage.extra.prefill_tokens_per_s ?? null,
      });
    }
  }
}

export async function interruptGeneration() {
  if (engine) {
    await engine.interruptGenerate();
  }
}
