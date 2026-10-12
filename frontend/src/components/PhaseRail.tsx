import { CheckCircle, Circle, WarningOctagon, XCircle } from "@phosphor-icons/react";
import {
  PHASE_LABELS,
  PHASE_ORDER,
  PHASE_SUBTITLES,
  type CompileResult,
  type PhaseKey,
} from "../lib/api";

type Status = "pending" | "done" | "failed" | "blocked";

export function phaseStatus(result: CompileResult | null, phase: PhaseKey): Status {
  if (!result) return "pending";
  if (result.failed_phase === phase) return "failed";

  const failedAt = result.failed_phase
    ? PHASE_ORDER.indexOf(result.failed_phase as PhaseKey)
    : -1;
  const here = PHASE_ORDER.indexOf(phase);
  if (failedAt >= 0 && here > failedAt) return "blocked";

  if (phase === "execution") return result.execution ? "done" : "blocked";
  return result.stages[phase as keyof CompileResult["stages"]] ? "done" : "pending";
}

function duration(result: CompileResult | null, phase: PhaseKey): number | null {
  if (!result) return null;
  if (phase === "execution") return result.execution?.duration_ms ?? null;
  const stage = result.stages[phase as keyof CompileResult["stages"]] as
    | { duration_ms?: number }
    | undefined;
  return stage?.duration_ms ?? null;
}

const ICONS: Record<Status, typeof Circle> = {
  pending: Circle,
  done: CheckCircle,
  failed: XCircle,
  blocked: WarningOctagon,
};

const ICON_TONE: Record<Status, string> = {
  pending: "text-rule",
  done: "text-verify",
  failed: "text-fault",
  blocked: "text-rule",
};

interface Props {
  result: CompileResult | null;
  active: PhaseKey;
  onSelect: (phase: PhaseKey) => void;
  running: boolean;
}

/** Below the rail breakpoint the same eight stops become a horizontal strip. */
export function PhaseStrip({ result, active, onSelect }: Omit<Props, "running">) {
  return (
    <nav
      aria-label="Compiler phases"
      className="flex gap-5 overflow-x-auto border-b border-rule px-5 py-2 lg:hidden"
    >
      {PHASE_ORDER.map((phase, i) => {
        const status = phaseStatus(result, phase);
        const isActive = active === phase;
        return (
          <button
            key={phase}
            type="button"
            onClick={() => onSelect(phase)}
            disabled={status === "pending" && !!result}
            aria-current={isActive ? "step" : undefined}
            className={[
              "flex shrink-0 items-center gap-1.5 whitespace-nowrap font-mono text-micro uppercase transition-colors",
              isActive ? "text-signal" : "text-muted hover:text-paper",
              status === "pending" && result ? "opacity-40" : "",
            ].join(" ")}
          >
            <span className="tnum">{String(i + 1).padStart(2, "0")}</span>
            {PHASE_LABELS[phase]}
            {status === "failed" && <XCircle size={11} weight="fill" className="text-fault" />}
          </button>
        );
      })}
    </nav>
  );
}

export function PhaseRail({ result, active, onSelect, running }: Props) {
  return (
    <nav aria-label="Compiler phases" className="flex h-full flex-col">
      <header className="flex items-baseline justify-between border-b border-rule px-5 py-3">
        <span className="field-label">Pipeline</span>
        {result?.stages.total_duration_ms != null && (
          <span className="tnum font-mono text-micro text-muted">
            {result.stages.total_duration_ms.toFixed(2)} ms
          </span>
        )}
      </header>

      <ol className="flex-1 overflow-y-auto py-1">
        {PHASE_ORDER.map((phase, i) => {
          const status = phaseStatus(result, phase);
          const Icon = ICONS[status];
          const ms = duration(result, phase);
          const isActive = active === phase;
          const reachable = status !== "pending" || !result;

          return (
            <li key={phase}>
              <button
                type="button"
                onClick={() => onSelect(phase)}
                disabled={!reachable}
                aria-current={isActive ? "step" : undefined}
                className={[
                  "group relative flex w-full items-start gap-3 px-5 py-2.5 text-left",
                  "border-l-2 transition-colors duration-150",
                  isActive
                    ? "border-signal bg-ink-2"
                    : "border-transparent hover:bg-ink-2/60",
                  reachable ? "cursor-pointer" : "cursor-default opacity-40",
                ].join(" ")}
              >
                <span className="tnum mt-[3px] w-4 shrink-0 font-mono text-micro text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>

                <span className="min-w-0 flex-1">
                  <span
                    className={[
                      "prose-sans block truncate text-[13px] leading-tight",
                      isActive ? "text-paper" : "text-paper/75",
                    ].join(" ")}
                  >
                    {PHASE_LABELS[phase]}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-micro text-muted">
                    {PHASE_SUBTITLES[phase]}
                  </span>
                </span>

                <span className="flex shrink-0 items-center gap-2 pt-[2px]">
                  {ms != null && (
                    <span className="tnum font-mono text-micro text-muted">
                      {ms.toFixed(2)}
                    </span>
                  )}
                  <Icon
                    size={13}
                    weight={status === "pending" ? "regular" : "fill"}
                    className={[
                      ICON_TONE[status],
                      running && status === "pending" ? "animate-pulse" : "",
                    ].join(" ")}
                  />
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
