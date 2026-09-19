/**
 * FIREWING JS/TS SDK.
 *
 * Minimal fetch-based client — no dependencies. Works in Node 18+
 * (built-in fetch) and modern browsers.
 *
 * Usage:
 *   import { FirewingClient } from "./firewing-sdk";
 *   const client = new FirewingClient("http://localhost:8000", apiKey);
 *   const reply = await client.chat([{ role: "user", content: "Hello" }]);
 *   for await (const chunk of client.chatStream([{ role: "user", content: "Hello" }])) {
 *     process.stdout.write(chunk);
 *   }
 */

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  model?: string;
  temperature?: number;
  topP?: number;
  maxTokens?: number;
  persona?: string;
}

export class FirewingError extends Error {
  requestId?: string;
  constructor(message: string, requestId?: string) {
    super(message);
    this.name = "FirewingError";
    this.requestId = requestId;
  }
}

export class FirewingClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  private headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
    };
  }

  async health(): Promise<{ status: string; version: string }> {
    const resp = await fetch(`${this.baseUrl}/health`);
    if (!resp.ok) throw new FirewingError(`HTTP ${resp.status}`);
    return resp.json();
  }

  async chat(messages: ChatMessage[], opts: ChatOptions = {}): Promise<string> {
    const resp = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        model: opts.model ?? "firewing-1.0-beta",
        messages,
        temperature: opts.temperature ?? 0.7,
        top_p: opts.topP ?? 0.9,
        max_tokens: opts.maxTokens ?? 1024,
        stream: false,
        persona: opts.persona ?? null,
      }),
    });
    if (!resp.ok) await this.throwForError(resp);
    const data = await resp.json();
    return data.choices[0].message.content;
  }

  async *chatStream(messages: ChatMessage[], opts: ChatOptions = {}): AsyncGenerator<string> {
    const resp = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        model: opts.model ?? "firewing-1.0-beta",
        messages,
        temperature: opts.temperature ?? 0.7,
        top_p: opts.topP ?? 0.9,
        max_tokens: opts.maxTokens ?? 1024,
        stream: true,
        persona: opts.persona ?? null,
      }),
    });
    if (!resp.ok || !resp.body) await this.throwForError(resp);

    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice("data: ".length);
        if (payload === "[DONE]") return;
        yield payload;
      }
    }
  }

  private async throwForError(resp: Response): Promise<never> {
    let message = `HTTP ${resp.status}`;
    let requestId: string | undefined;
    try {
      const data = await resp.json();
      if (data?.error) {
        message = data.error.message ?? message;
        requestId = data.error.request_id;
      }
    } catch {
      // response wasn't JSON — fall back to the status-only message
    }
    throw new FirewingError(message, requestId);
  }
}
