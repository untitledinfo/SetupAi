export type Role = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  systemPrompt: string;
  modelId: string;
  temperature: number;
  topP: number;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export interface ModelOption {
  id: string;
  label: string;
  size: string;
  vram: string;
  tagline: string;
}

export type EngineStatus =
  | "idle"
  | "downloading"
  | "compiling"
  | "ready"
  | "generating"
  | "error"
  | "unsupported";
