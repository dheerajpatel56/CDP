import { Check, Warning, X } from "@phosphor-icons/react";
import type { Severity, Stages } from "../../lib/api";
import { Panel } from "../Panel";

const MARK: Record<Severity, { Icon: typeof Check; tone: string }> = {
  pass: { Icon: Check, tone: "text-verify" },
  warning: { Icon: Warning, tone: "text-signal" },
  error: { Icon: X, tone: "text-fault" },
};

export function SecurityPanel({ data }: { data: Stages["security_analysis"] }) {
  return (
    <Panel
      title="Security analysis"
      note={data.safe ? "statement cleared for execution" : "execution blocked"}
    >
      <div className="grid grid-cols-2 border-b border-rule sm:grid-cols-4">
        <Stat label="Verdict" value={data.safe ? "Pass" : "Blocked"} tone={data.safe ? "text-verify" : "text-fault"} />
        <Stat label="Bound params" value={String(data.parameter_count)} />
        <Stat label="Joins" value={String(data.join_count)} />
        <Stat label="Row cap" value={data.row_cap.toLocaleString()} />
      </div>

      <div className="border-b border-rule px-5 py-4">
        <p className="field-label mb-2">Relations reached</p>
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          {data.tables_accessed.map((t) => (
            <span key={t} className="font-mono text-[12.5px] text-paper">
              {t}
            </span>
          ))}
        </div>
      </div>

      <div className="px-5 py-4">
        <p className="field-label mb-3">Checks</p>
        <ul className="space-y-2">
          {data.findings.map((f, i) => {
            const { Icon, tone } = MARK[f.severity];
            return (
              <li key={i} className="flex items-start gap-2.5">
                <Icon size={12} weight="bold" className={`mt-[3px] shrink-0 ${tone}`} />
                <span className="prose-sans max-w-[72ch] text-[12.5px] leading-relaxed text-paper/85">
                  {f.message}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </Panel>
  );
}

function Stat({ label, value, tone = "text-paper" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="border-r border-rule px-5 py-4 last:border-r-0">
      <p className="field-label mb-1.5">{label}</p>
      <p className={`tnum font-mono text-[15px] ${tone}`}>{value}</p>
    </div>
  );
}
