"use client";

import { useRef, useState, KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";

export default function Composer({
  onSend,
  onStop,
  isGenerating,
  disabled,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  isGenerating: boolean;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled || isGenerating) return;
    onSend(text);
    setValue("");
    if (ref.current) ref.current.style.height = "auto";
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const autoGrow = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <div className="border-t border-ink-600 bg-ink-950/70 p-3">
      <div className="max-w-3xl mx-auto flex items-end gap-2 rounded-2xl border border-ink-600 bg-ink-800/70 focus-within:border-volt-500/60 focus-within:shadow-glow-sm px-3 py-2">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            autoGrow();
          }}
          onKeyDown={onKeyDown}
          disabled={disabled}
          rows={1}
          placeholder={
            disabled ? "Loading model…" : "Message SetupAI — Enter to send, Shift+Enter for a new line"
          }
          className="flex-1 resize-none bg-transparent text-[15px] text-steel-100 placeholder:text-steel-400 focus:outline-none py-1.5 max-h-[200px] disabled:opacity-50"
        />
        {isGenerating ? (
          <button
            onClick={onStop}
            className="shrink-0 w-9 h-9 rounded-xl bg-ink-700 border border-ink-600 hover:border-signal-red/50 text-steel-200 hover:text-signal-red flex items-center justify-center transition-colors"
            aria-label="Stop generating"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={disabled || !value.trim()}
            className="shrink-0 w-9 h-9 rounded-xl bg-volt-600 hover:bg-volt-500 disabled:opacity-30 disabled:hover:bg-volt-600 text-ink-950 flex items-center justify-center transition-colors shadow-glow-sm"
            aria-label="Send message"
          >
            <ArrowUp size={16} />
          </button>
        )}
      </div>
      <p className="text-center text-[10px] text-steel-400 mt-2">
        Runs on your device. Nothing you type ever leaves your browser.
      </p>
    </div>
  );
}
