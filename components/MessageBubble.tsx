"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Bot, User, Copy, Check } from "lucide-react";
import { useState } from "react";
import type { ChatMessage } from "@/lib/types";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`shrink-0 mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center border ${
          isUser
            ? "bg-ink-700 border-ink-600 text-steel-300"
            : "bg-volt-600/15 border-volt-500/40 text-volt-400 shadow-glow-sm"
        }`}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </div>

      <div
        className={`group relative max-w-[78%] rounded-2xl px-4 py-3 border ${
          isUser
            ? "bg-ink-700/80 border-ink-600 rounded-tr-sm"
            : "bg-ink-800/70 border-ink-600 rounded-tl-sm"
        }`}
      >
        {message.content ? (
          <div className="prose-setupai text-[15px]">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : (
          <span className="inline-flex gap-1 py-1">
            <span className="w-1.5 h-1.5 rounded-full bg-volt-400 animate-pulseGlow" />
            <span className="w-1.5 h-1.5 rounded-full bg-volt-400 animate-pulseGlow [animation-delay:0.2s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-volt-400 animate-pulseGlow [animation-delay:0.4s]" />
          </span>
        )}

        {message.content && (
          <button
            onClick={copy}
            aria-label="Copy message"
            className="absolute -top-2.5 -right-2.5 opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 rounded-md bg-ink-700 border border-ink-600 flex items-center justify-center text-steel-400 hover:text-volt-400 hover:border-volt-500/50"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        )}
      </div>
    </div>
  );
}
