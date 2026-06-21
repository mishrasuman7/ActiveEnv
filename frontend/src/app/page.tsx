"use client";

import { useState } from "react";
import {
  approveFix,
  createRun,
  getRun,
  inferRun,
  probeRun,
  undoFix,
  type Run,
} from "@/lib/api";
import { EXAMPLE_CONFIG, EXAMPLE_FILES, SUGGESTED_FIX } from "@/lib/example";
import FindingCard from "@/components/FindingCard";

type Step = "idle" | "ingest" | "infer" | "probe" | "done";

const STEPS: { key: Step; label: string }[] = [
  { key: "ingest", label: "Observe" },
  { key: "infer", label: "Infer intent" },
  { key: "probe", label: "Probe reality" },
];

export default function Home() {
  const [config, setConfig] = useState("");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [env, setEnv] = useState("production");
  const [run, setRun] = useState<Run | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [intentOff, setIntentOff] = useState(false);
  const [error, setError] = useState("");

  function loadExample() {
    setConfig(EXAMPLE_CONFIG);
    setFiles(EXAMPLE_FILES);
    setRun(null);
    setStep("idle");
    setError("");
  }

  async function runAll() {
    setError("");
    setRun(null);
    setIntentOff(false);
    try {
      setStep("ingest");
      let r = await createRun({
        config_text: config,
        files,
        target_environment: env,
      });
      setRun(r);

      setStep("infer");
      try {
        r = await inferRun(r.id);
        setRun(r);
      } catch (e) {
        if ((e as { status?: number }).status === 503) setIntentOff(true);
        else throw e;
      }

      setStep("probe");
      await probeRun(r.id);
      r = await getRun(r.id);
      setRun(r);
      setStep("done");
    } catch (e) {
      setError(String((e as Error).message || e));
      setStep("idle");
    }
  }

  async function refresh() {
    if (run) setRun(await getRun(run.id));
  }
  async function onApprove(findingId: number, value: string) {
    await approveFix(findingId, value);
    await refresh();
  }
  async function onUndo(findingId: number) {
    await undoFix(findingId);
    await refresh();
  }

  const busy = step !== "idle" && step !== "done";
  const findings = run?.keys.filter((k) => k.finding) ?? [];
  const inventory = run?.keys.filter((k) => !k.finding) ?? [];
  const summary = run?.findings_summary ?? {
    correct: 0,
    suspect: 0,
    silently_wrong: 0,
    unknown: 0,
  };

  return (
    <div className="max-w-6xl mx-auto px-5 py-8">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <span
            className="text-2xl font-bold"
            style={{ color: "var(--foreground)" }}
          >
            Active<span style={{ color: "var(--teal)" }}>Env</span>
          </span>
          <span
            className="text-[10px] px-2 py-0.5 rounded-full mono"
            style={{ background: "var(--surface-2)", color: "var(--muted)" }}
          >
            autopilot · read-only probes
          </span>
        </div>
        <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
          Catches the config value that is present, valid, authenticating — and
          still silently wrong.
        </p>
      </header>

      <div className="grid md:grid-cols-[380px_1fr] gap-5">
        <section className="card p-4 h-fit">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold">Config + codebase</h2>
            <button
              onClick={loadExample}
              className="text-[11px] mono"
              style={{ color: "var(--teal)" }}
            >
              load example
            </button>
          </div>
          <textarea
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            placeholder="Paste your .env / settings.py / yaml / json…"
            rows={10}
            className="w-full px-3 py-2 rounded text-xs mono resize-y"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          />
          <div className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
            {Object.keys(files).length > 0
              ? `+ ${Object.keys(files).length} code files attached`
              : "no code files attached (optional)"}
          </div>

          <div className="flex items-center gap-2 mt-3">
            <label className="text-xs" style={{ color: "var(--muted)" }}>
              target env
            </label>
            <select
              value={env}
              onChange={(e) => setEnv(e.target.value)}
              className="px-2 py-1.5 rounded text-xs"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
            >
              <option value="production">production</option>
              <option value="staging">staging</option>
              <option value="development">development</option>
            </select>
            <button
              onClick={runAll}
              disabled={busy || !config.trim()}
              className="ml-auto px-4 py-1.5 rounded text-sm font-semibold disabled:opacity-50"
              style={{ background: "var(--teal)", color: "#06231f" }}
            >
              {busy ? "running…" : "Run"}
            </button>
          </div>
          {error && (
            <p className="text-xs mt-2" style={{ color: "var(--red)" }}>
              {error}
            </p>
          )}
        </section>

        <section>
          <div className="card p-3 mb-4 flex items-center gap-2">
            {STEPS.map((s, i) => {
              const order: Step[] = ["ingest", "infer", "probe", "done"];
              const active = order.indexOf(step) >= order.indexOf(s.key);
              const skipped = s.key === "infer" && intentOff;
              return (
                <div key={s.key} className="flex items-center gap-2 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-5 h-5 rounded-full text-[10px] flex items-center justify-center font-bold"
                      style={{
                        background: active ? "var(--teal)" : "var(--surface-2)",
                        color: active ? "#06231f" : "var(--muted)",
                      }}
                    >
                      {i + 1}
                    </span>
                    <span
                      className="text-xs"
                      style={{
                        color: active ? "var(--foreground)" : "var(--muted)",
                      }}
                    >
                      {s.label}
                      {skipped && (
                        <span style={{ color: "var(--amber)" }}> (no key)</span>
                      )}
                    </span>
                  </div>
                  {i < STEPS.length - 1 && (
                    <div
                      className="flex-1 h-px"
                      style={{ background: "var(--border)" }}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {!run && (
            <div
              className="card p-10 text-center text-sm"
              style={{ color: "var(--muted)" }}
            >
              Paste a config (or{" "}
              <b style={{ color: "var(--teal)" }}>load example</b>) and hit Run.
              ActiveEnv infers intent from your code, probes the real systems,
              and flags the silent ones.
            </div>
          )}

          {run && (
            <>
              <div className="grid grid-cols-3 gap-3 mb-4">
                <Stat
                  label="silently wrong"
                  value={summary.silently_wrong}
                  color="#f87171"
                />
                <Stat label="suspect" value={summary.suspect} color="#fbbf24" />
                <Stat label="correct" value={summary.correct} color="#34d399" />
              </div>

              <div className="space-y-3">
                {findings.map((ck) => (
                  <FindingCard
                    key={ck.id}
                    ck={ck}
                    suggestedFix={SUGGESTED_FIX[ck.name]}
                    onApprove={onApprove}
                    onUndo={onUndo}
                  />
                ))}
              </div>

              {inventory.length > 0 && (
                <div className="card p-3 mt-4">
                  <div
                    className="text-[11px] mb-2"
                    style={{ color: "var(--muted)" }}
                  >
                    other config ({inventory.length}) — parsed, not probeable
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {inventory.map((k) => (
                      <span
                        key={k.id}
                        className="mono text-[11px] px-2 py-1 rounded"
                        style={{
                          background: "var(--surface-2)",
                          color: "var(--muted)",
                        }}
                      >
                        {k.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {run.audit && run.audit.length > 0 && (
                <div className="card p-3 mt-4">
                  <div
                    className="text-[11px] mb-2"
                    style={{ color: "var(--muted)" }}
                  >
                    audit log
                  </div>
                  <div className="space-y-1">
                    {run.audit.map((a) => (
                      <div
                        key={a.id}
                        className="mono text-[11px] flex gap-2"
                        style={{ color: "var(--muted)" }}
                      >
                        <span style={{ color: "var(--teal)" }}>{a.action}</span>
                        <span className="truncate">
                          {JSON.stringify(a.detail)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="card p-3">
      <div className="text-2xl font-bold" style={{ color }}>
        {value}
      </div>
      <div className="text-[11px]" style={{ color: "var(--muted)" }}>
        {label}
      </div>
    </div>
  );
}
