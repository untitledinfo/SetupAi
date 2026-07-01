"use client";

import { Plus, MessageSquare, Trash2, Cpu, Zap } from "lucide-react";
import type { Conversation, ModelOption } from "@/lib/types";

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  models,
  activeModelId,
  onModelChange,
  disabled,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  models: ModelOption[];
  activeModelId: string;
  onModelChange: (id: string) => void;
  disabled: boolean;
}) {
  return (
    <aside className="w-72 shrink-0 border-r border-ink-600 bg-ink-950/60 flex flex-col h-full">
      <div className="px-4 pt-5 pb-4 border-b border-ink-600">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-volt-600/15 border border-volt-500/40 flex items-center justify-center shadow-glow-sm">
            <Zap size={16} className="text-volt-400" />
          </div>
          <div>
            <h1 className="font-display text-steel-100 text-[15px] tracking-wide leading-none">
              SetupAI
            </h1>
            <p className="text-[10px] text-steel-400 mt-1 tracking-wide uppercase">
              Fully offline · No API key
            </p>
          </div>
        </div>
      </div>

      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-volt-600 hover:bg-volt-500 transition-colors text-ink-950 font-medium text-sm py-2.5 shadow-glow-sm"
        >
          <Plus size={16} />
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 space-y-1">
        {conversations.length === 0 && (
          <p className="text-xs text-steel-400 px-2 py-4 text-center">
            Your conversations will appear here.
          </p>
        )}
        {conversations
          .slice()
          .sort((a, b) => b.updatedAt - a.updatedAt)
          .map((c) => (
            <div
              key={c.id}
              onClick={() => onSelect(c.id)}
              className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 cursor-pointer border ${
                c.id === activeId
                  ? "bg-ink-700 border-ink-600"
                  : "border-transparent hover:bg-ink-800/70"
              }`}
            >
              <MessageSquare size={14} className="text-steel-400 shrink-0" />
              <span className="text-sm text-steel-200 truncate flex-1">{c.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(c.id);
                }}
                className="opacity-0 group-hover:opacity-100 text-steel-400 hover:text-signal-red transition-opacity"
                aria-label="Delete conversation"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
      </div>

      <div className="p-3 border-t border-ink-600">
        <label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-steel-400 mb-2">
          <Cpu size={12} />
          Local model
        </label>
        <select
          value={activeModelId}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={disabled}
          className="w-full bg-ink-800 border border-ink-600 rounded-lg text-sm text-steel-100 px-2.5 py-2 focus:border-volt-500 disabled:opacity-50"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label} — {m.size}
            </option>
          ))}
        </select>
        <p className="text-[10px] text-steel-400 mt-2 leading-relaxed">
          Switching models re-downloads once, then caches in your browser for offline use.
        </p>
      </div>
    </aside>
  );
}
