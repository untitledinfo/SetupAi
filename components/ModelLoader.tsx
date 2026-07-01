"use client";

import { Cpu, HardDriveDownload, CheckCircle2, AlertTriangle } from "lucide-react";
import type { EngineStatus } from "@/lib/types";

export default function ModelLoader({
  status,
  progress,
  text,
  modelLabel,
}: {
  status: EngineStatus;
  progress: number; // 0..1
  text: string;
  modelLabel: string;
}) {
  const pct = Math.round(progress * 100);

  if (status === "unsupported") {
    return (
      <div className="mx-auto max-w-md text-center border border-signal.red/30 rounded-2xl p-6 bg-ink-800/60">
        <AlertTriangle className="mx-auto mb-3 text-signal-red" size={26} />
        <h3 className="font-display text-steel-100 text-lg mb-1">WebGPU not available</h3>
        <p className="text-sm text-steel-400">
          SetupAI runs the model fully in-browser via WebGPU. Your current browser doesn&apos;t
          expose it — try the latest Chrome, Edge, or Firefox Nightly with WebGPU enabled.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md w-full">
      <div className="rounded-2xl border border-ink-600 bg-ink-800/60 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-volt-600/15 border border-volt-500/40 flex items-center justify-center shadow-glow-sm">
            {status === "ready" ? (
              <CheckCircle2 className="text-signal-green" size={18} />
            ) : status === "downloading" ? (
              <HardDriveDownload className="text-volt-400" size={18} />
            ) : (
              <Cpu className="text-volt-400" size={18} />
            )}
          </div>
          <div>
            <div className="font-display text-sm text-steel-100 tracking-wide">
              {modelLabel}
            </div>
            <div className="text-xs text-steel-400">
              {status === "downloading" && "Downloading weights to your browser cache…"}
              {status === "compiling" && "Compiling for your GPU…"}
              {status === "ready" && "Loaded — running fully offline"}
              {status === "idle" && "Waiting to start"}
              {status === "error" && "Something went wrong"}
            </div>
          </div>
        </div>

        <div className="h-2 rounded-full bg-ink-700 overflow-hidden border border-ink-600">
          <div
            className="h-full bg-gradient-to-r from-volt-700 via-volt-500 to-volt-300 transition-all duration-300"
            style={{ width: `${Math.max(pct, status === "ready" ? 100 : 3)}%` }}
          />
        </div>

        <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-steel-400">
          <span className="truncate pr-2">{text || "Preparing…"}</span>
          <span>{pct}%</span>
        </div>

        <p className="mt-4 text-[11px] text-steel-400 leading-relaxed">
          One-time download, cached by your browser. Every run after this loads instantly and
          works with no internet connection, no API key, and no server.
        </p>
      </div>
    </div>
  );
}
