"use client";

import { useEffect, useRef, useState } from "react";
import type { InitProgressReport } from "@mlc-ai/web-llm";
import Sidebar from "@/components/Sidebar";
import Composer from "@/components/Composer";
import MessageBubble from "@/components/MessageBubble";
import ModelLoader from "@/components/ModelLoader";
import {
  MODEL_OPTIONS,
  DEFAULT_MODEL_ID,
  DEFAULT_SYSTEM_PROMPT,
  DEFAULT_TEMPERATURE,
  DEFAULT_TOP_P,
} from "@/lib/models";
import { loadConversations, saveConversations, newId } from "@/lib/storage";
import {
  streamChatCompletion,
  interruptGeneration,
  isWebGPUSupported,
  unloadEngine,
  type GenerationStats,
} from "@/lib/engine";
import type { ChatMessage, Conversation, EngineStatus } from "@/lib/types";
import { Settings2, Download, RotateCcw, Pencil, Check, Power, AlertTriangle } from "lucide-react";

function makeConversation(modelId: string): Conversation {
  const now = Date.now();
  return {
    id: newId(),
    title: "New chat",
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    modelId,
    temperature: DEFAULT_TEMPERATURE,
    topP: DEFAULT_TOP_P,
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export default function Page() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [status, setStatus] = useState<EngineStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [stats, setStats] = useState<GenerationStats | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const lastActionRef = useRef<(() => void) | null>(null);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  // Load persisted conversations once on mount.
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (!isWebGPUSupported()) {
      setStatus("unsupported");
    }

    const stored = loadConversations();
    if (stored.length > 0) {
      // Backfill fields for conversations saved by an older version of the app.
      const migrated = stored.map((c) => ({
        ...c,
        temperature: c.temperature ?? DEFAULT_TEMPERATURE,
        topP: c.topP ?? DEFAULT_TOP_P,
      }));
      setConversations(migrated);
      setActiveId(migrated.slice().sort((a, b) => b.updatedAt - a.updatedAt)[0].id);
    } else {
      const c = makeConversation(DEFAULT_MODEL_ID);
      setConversations([c]);
      setActiveId(c.id);
    }
  }, []);

  useEffect(() => {
    if (conversations.length > 0) saveConversations(conversations);
  }, [conversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [active?.messages.length, active?.messages[active.messages.length - 1]?.content]);

  const updateConversation = (id: string, patch: Partial<Conversation>) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, ...patch, updatedAt: Date.now() } : c))
    );
  };

  const handleNewChat = () => {
    const modelId = active?.modelId ?? DEFAULT_MODEL_ID;
    const c = makeConversation(modelId);
    setConversations((prev) => [c, ...prev]);
    setActiveId(c.id);
    setErrorMessage(null);
  };

  const handleDelete = (id: string) => {
    setConversations((prev) => {
      const next = prev.filter((c) => c.id !== id);
      if (id === activeId) {
        setActiveId(next[0]?.id ?? null);
      }
      return next;
    });
  };

  const handleModelChange = async (modelId: string) => {
    if (!active) return;
    // Loading a new model invalidates any in-flight load for the old one.
    await unloadEngine();
    setStatus(isWebGPUSupported() ? "idle" : "unsupported");
    setProgress(0);
    setProgressText("");
    updateConversation(active.id, { modelId });
  };

  const handleResetModel = async () => {
    await unloadEngine();
    setStatus(isWebGPUSupported() ? "idle" : "unsupported");
    setProgress(0);
    setProgressText("");
    setErrorMessage(null);
  };

  const onProgress = (report: InitProgressReport) => {
    const text = report.text ?? "";
    setProgressText(text);
    if (typeof report.progress === "number") setProgress(report.progress);
    if (/download/i.test(text)) setStatus("downloading");
    else if (/compil|load/i.test(text)) setStatus("compiling");
  };

  const runGeneration = async (conversation: Conversation, messages: ChatMessage[]) => {
    setIsGenerating(true);
    setErrorMessage(null);
    setStats(null);
    setStatus((s) => (s === "unsupported" ? s : "downloading"));
    lastActionRef.current = () => runGeneration(conversation, messages);

    const assistantMsg: ChatMessage = {
      id: newId(),
      role: "assistant",
      content: "",
      createdAt: Date.now(),
    };

    updateConversation(conversation.id, {
      messages: [...messages, assistantMsg],
    });

    try {
      let acc = "";
      for await (const delta of streamChatCompletion(
        conversation.modelId,
        conversation.systemPrompt,
        messages,
        { temperature: conversation.temperature, topP: conversation.topP },
        onProgress,
        setStats
      )) {
        acc += delta;
        setStatus("generating");
        setConversations((prev) =>
          prev.map((c) =>
            c.id === conversation.id
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === assistantMsg.id ? { ...m, content: acc } : m
                  ),
                }
              : c
          )
        );
      }
      setStatus("ready");
    } catch (err) {
      setStatus("error");
      const message =
        err instanceof Error ? err.message : "Generation was interrupted or failed.";
      setErrorMessage(message);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversation.id
            ? {
                ...c,
                // Drop the empty placeholder rather than leaving a blank bubble;
                // the error banner above the composer explains what happened.
                messages: c.messages.filter(
                  (m) => !(m.id === assistantMsg.id && !m.content)
                ),
              }
            : c
        )
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSend = async (text: string) => {
    if (!active) return;

    const userMsg: ChatMessage = {
      id: newId(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    const nextMessages = [...active.messages, userMsg];
    const isFirst = active.messages.length === 0;

    updateConversation(active.id, {
      messages: nextMessages,
      title: isFirst ? text.slice(0, 40) : active.title,
    });

    await runGeneration({ ...active, messages: nextMessages }, nextMessages);
  };

  const handleStop = async () => {
    await interruptGeneration();
    setIsGenerating(false);
    setStatus("ready");
  };

  const handleRegenerate = async () => {
    if (!active || active.messages.length === 0) return;
    const trimmed = [...active.messages];
    while (trimmed.length && trimmed[trimmed.length - 1].role === "assistant") trimmed.pop();
    if (!trimmed.length) return;
    updateConversation(active.id, { messages: trimmed });
    await runGeneration({ ...active, messages: trimmed }, trimmed);
  };

  const handleExport = () => {
    if (!active) return;
    const md = active.messages
      .map((m) => `### ${m.role === "user" ? "You" : "SetupAI"}\n\n${m.content}`)
      .join("\n\n---\n\n");
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${active.title || "setupai-chat"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const startRename = () => {
    if (!active) return;
    setTitleDraft(active.title);
    setRenaming(true);
  };

  const commitRename = () => {
    if (active && titleDraft.trim()) {
      updateConversation(active.id, { title: titleDraft.trim().slice(0, 60) });
    }
    setRenaming(false);
  };

  const activeModel = MODEL_OPTIONS.find((m) => m.id === active?.modelId) ?? MODEL_OPTIONS[0];
  const engineBusy = status === "downloading" || status === "compiling";
  const modelControlsDisabled = isGenerating || engineBusy;

  return (
    <main className="flex h-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => {
          setActiveId(id);
          setErrorMessage(null);
        }}
        onNew={handleNewChat}
        onDelete={handleDelete}
        models={MODEL_OPTIONS}
        activeModelId={active?.modelId ?? DEFAULT_MODEL_ID}
        onModelChange={handleModelChange}
        disabled={modelControlsDisabled}
      />

      <section className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-ink-600 flex items-center justify-between px-5 shrink-0 gap-3">
          <div className="flex items-center gap-2 min-w-0">
            {renaming ? (
              <div className="flex items-center gap-1.5">
                <input
                  autoFocus
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && commitRename()}
                  onBlur={commitRename}
                  className="bg-ink-800 border border-volt-500/50 rounded-md text-sm text-steel-100 px-2 py-1 focus:outline-none w-48"
                />
                <button onClick={commitRename} className="text-volt-400" aria-label="Save title">
                  <Check size={14} />
                </button>
              </div>
            ) : (
              <button
                onClick={startRename}
                className="flex items-center gap-1.5 group min-w-0"
                title="Rename conversation"
              >
                <span className="text-sm text-steel-200 truncate">
                  {active?.title ?? "SetupAI"}
                </span>
                <Pencil
                  size={11}
                  className="text-steel-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                />
              </button>
            )}
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-ink-600 text-steel-400 font-mono shrink-0">
              {activeModel.label}
            </span>
            {stats?.decodeTokensPerSec != null && (
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-signal-green/30 text-signal-green font-mono shrink-0">
                {stats.decodeTokensPerSec.toFixed(1)} tok/s
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={handleResetModel}
              disabled={engineBusy}
              className="w-8 h-8 rounded-lg hover:bg-ink-800 text-steel-400 hover:text-signal-amber flex items-center justify-center disabled:opacity-30 transition-colors"
              aria-label="Unload model"
              title="Unload model from memory / reset a stuck load"
            >
              <Power size={15} />
            </button>
            <button
              onClick={handleExport}
              disabled={!active?.messages.length}
              className="w-8 h-8 rounded-lg hover:bg-ink-800 text-steel-400 hover:text-steel-100 flex items-center justify-center disabled:opacity-30 transition-colors"
              aria-label="Export chat"
              title="Export chat as Markdown"
            >
              <Download size={15} />
            </button>
            <button
              onClick={handleRegenerate}
              disabled={!active?.messages.length || isGenerating}
              className="w-8 h-8 rounded-lg hover:bg-ink-800 text-steel-400 hover:text-steel-100 flex items-center justify-center disabled:opacity-30 transition-colors"
              aria-label="Regenerate last response"
              title="Regenerate last response"
            >
              <RotateCcw size={15} />
            </button>
            <button
              onClick={() => setShowSettings((s) => !s)}
              className={`w-8 h-8 rounded-lg hover:bg-ink-800 flex items-center justify-center transition-colors ${
                showSettings ? "text-volt-400 bg-ink-800" : "text-steel-400 hover:text-steel-100"
              }`}
              aria-label="Settings"
              title="Generation settings"
            >
              <Settings2 size={15} />
            </button>
          </div>
        </header>

        {showSettings && active && (
          <div className="border-b border-ink-600 bg-ink-900/60 px-5 py-3 space-y-3">
            <div>
              <label className="text-[11px] uppercase tracking-wide text-steel-400 mb-1.5 block">
                System prompt
              </label>
              <textarea
                value={active.systemPrompt}
                onChange={(e) => updateConversation(active.id, { systemPrompt: e.target.value })}
                rows={2}
                className="w-full bg-ink-800 border border-ink-600 rounded-lg text-sm text-steel-100 px-3 py-2 focus:border-volt-500 focus:outline-none resize-none"
              />
            </div>
            <div className="flex gap-6">
              <div className="flex-1">
                <label className="text-[11px] uppercase tracking-wide text-steel-400 mb-1.5 flex justify-between">
                  <span>Temperature</span>
                  <span className="font-mono text-steel-300">{active.temperature.toFixed(2)}</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={1.5}
                  step={0.05}
                  value={active.temperature}
                  onChange={(e) =>
                    updateConversation(active.id, { temperature: parseFloat(e.target.value) })
                  }
                  className="w-full accent-volt-500"
                />
              </div>
              <div className="flex-1">
                <label className="text-[11px] uppercase tracking-wide text-steel-400 mb-1.5 flex justify-between">
                  <span>Top P</span>
                  <span className="font-mono text-steel-300">{active.topP.toFixed(2)}</span>
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={1}
                  step={0.05}
                  value={active.topP}
                  onChange={(e) =>
                    updateConversation(active.id, { topP: parseFloat(e.target.value) })
                  }
                  className="w-full accent-volt-500"
                />
              </div>
            </div>
          </div>
        )}

        {errorMessage && (
          <div className="border-b border-signal-red/30 bg-signal-red/10 px-5 py-2.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-signal-red text-sm min-w-0">
              <AlertTriangle size={14} className="shrink-0" />
              <span className="truncate">{errorMessage}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => lastActionRef.current?.()}
                className="text-xs px-2.5 py-1 rounded-md border border-signal-red/40 text-signal-red hover:bg-signal-red/10"
              >
                Retry
              </button>
              <button
                onClick={() => setErrorMessage(null)}
                className="text-xs text-steel-400 hover:text-steel-200"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5">
          {!active || active.messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              {status === "unsupported" ? (
                <ModelLoader status={status} progress={0} text="" modelLabel={activeModel.label} />
              ) : engineBusy ? (
                <ModelLoader
                  status={status}
                  progress={progress}
                  text={progressText}
                  modelLabel={activeModel.label}
                />
              ) : (
                <div className="text-center max-w-sm">
                  <h2 className="font-display text-xl text-steel-100 mb-2">
                    Ask SetupAI anything
                  </h2>
                  <p className="text-sm text-steel-400 leading-relaxed">
                    The model loads once into your browser and then runs completely offline —
                    no API key, no account, no server round-trip.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto py-6 space-y-6">
              {active.messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
              {engineBusy && (
                <ModelLoader
                  status={status}
                  progress={progress}
                  text={progressText}
                  modelLabel={activeModel.label}
                />
              )}
            </div>
          )}
        </div>

        <Composer
          onSend={handleSend}
          onStop={handleStop}
          isGenerating={isGenerating}
          disabled={status === "unsupported"}
        />
      </section>
    </main>
  );
}
