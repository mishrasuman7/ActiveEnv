"use client";

import { useEffect, useRef, useState } from "react";
import type { ConfigKey, Classification } from "@/lib/api";

const STYLES: Record<
  Classification,
  { label: string; color: string; bg: string; dot: string }
> = {
  silently_wrong: {
    label: "SILENTLY WRONG",
    color: "#f87171",
    bg: "rgba(248,113,113,0.12)",
    dot: "#f87171",
  },
  suspect: {
    label: "SUSPECT",
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.12)",
    dot: "#fbbf24",
  },
  correct: {
    label: "CORRECT",
    color: "#34d399",
    bg: "rgba(52,211,153,0.12)",
    dot: "#34d399",
  },
  unknown: {
    label: "UNKNOWN",
    color: "#94a7c0",
    bg: "rgba(148,167,192,0.12)",
    dot: "#94a7c0",
  },
};

export default function FindingCard({
  ck,
  suggestedFix,
  onApprove,
  onUndo,
}: {
  ck: ConfigKey;
  suggestedFix?: string;
  onApprove: (findingId: number, value: string) => Promise<void>;
  onUndo: (findingId: number) => Promise<void>;
}) {
  const finding = ck.finding;
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const prevClass = useRef<Classification | undefined>(finding?.classification);

  // Flash green when a finding transitions to correct.
  useEffect(() => {
    if (
      finding &&
      finding.classification === "correct" &&
      prevClass.current &&
      prevClass.current !== "correct"
    ) {
      cardRef.current?.classList.remove("flash-green");
      void cardRef.current?.offsetWidth; // reflow to restart animation
      cardRef.current?.classList.add("flash-green");
    }
    prevClass.current = finding?.classification;
  }, [finding?.classification]);

  if (!finding) return null;
  const s = STYLES[finding.classification] ?? STYLES.unknown;
  const isWrong =
    finding.classification === "silently_wrong" ||
    finding.classification === "suspect";

  async function approve() {
    if (!finding) return;
    setBusy(true);
    try {
      await onApprove(finding.id, value || suggestedFix || "");
    } finally {
      setBusy(false);
    }
  }
  async function undo() {
    if (!finding) return;
    setBusy(true);
    try {
      await onUndo(finding.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      ref={cardRef}
      className="card p-4"
      style={{ borderColor: s.color + "55" }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="mono text-[15px] font-semibold truncate"
              style={{ color: "var(--foreground)" }}
            >
              {ck.name}
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded mono"
              style={{ background: "var(--surface-2)", color: "var(--muted)" }}
            >
              {ck.kind}
            </span>
          </div>
          <div className="mono text-xs mt-1" style={{ color: "var(--muted)" }}>
            {ck.masked_value}
          </div>
        </div>
        <span
          className="text-[10px] font-bold px-2 py-1 rounded-full whitespace-nowrap tracking-wide"
          style={{ color: s.color, background: s.bg }}
        >
          ● {s.label}
        </span>
      </div>

      <p className="text-sm mt-3" style={{ color: "var(--foreground)" }}>
        {finding.evidence}
      </p>

      {finding.blast_radius && isWrong && (
        <p
          className="text-xs mt-2 pl-3"
          style={{ color: s.color, borderLeft: `2px solid ${s.color}66` }}
        >
          {finding.blast_radius}
        </p>
      )}

      {ck.intent?.rationale && (
        <p className="text-xs mt-2 italic" style={{ color: "var(--muted)" }}>
          intent: {ck.intent.rationale}
        </p>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        className="text-[11px] mt-2 mono"
        style={{ color: "var(--teal)" }}
      >
        {open ? "▾ hide evidence" : "▸ expected vs reality"}
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-3 mt-2 text-[11px]">
          <Pre title="expected" obj={finding.expected} />
          <Pre title="reality" obj={finding.reality} />
        </div>
      )}

      {isWrong && (
        <div
          className="mt-3 pt-3"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <label className="text-[11px]" style={{ color: "var(--muted)" }}>
            corrected value (human approval required)
          </label>
          <div className="flex gap-2 mt-1">
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={suggestedFix || finding.proposed_fix}
              className="flex-1 px-2 py-1.5 rounded text-xs mono"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            />
            <button
              onClick={approve}
              disabled={busy}
              className="px-3 py-1.5 rounded text-xs font-semibold whitespace-nowrap"
              style={{ background: "var(--teal)", color: "#06231f" }}
            >
              {busy ? "probing…" : "Approve & re-probe"}
            </button>
          </div>
          {finding.proposed_fix && (
            <p className="text-[10px] mt-1" style={{ color: "var(--muted)" }}>
              suggestion: {finding.proposed_fix}
            </p>
          )}
        </div>
      )}

      {finding.classification === "correct" && (
        <div
          className="mt-3 pt-3 flex items-center justify-between"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <span className="text-xs" style={{ color: "var(--green)" }}>
            {finding.fixed
              ? "✓ fixed — re-probed and now matches intent"
              : "✓ correct — reality matches intent"}
          </span>
          {finding.fixed && (
            <button
              onClick={undo}
              disabled={busy}
              className="text-[11px] mono"
              style={{ color: "var(--muted)" }}
            >
              {busy ? "…" : "undo"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Pre({ title, obj }: { title: string; obj: Record<string, unknown> }) {
  return (
    <div>
      <div className="mono mb-1" style={{ color: "var(--muted)" }}>
        {title}
      </div>
      <pre
        className="mono p-2 rounded overflow-x-auto"
        style={{ background: "var(--surface-2)", color: "var(--foreground)" }}
      >
        {JSON.stringify(obj, null, 1)}
      </pre>
    </div>
  );
}
