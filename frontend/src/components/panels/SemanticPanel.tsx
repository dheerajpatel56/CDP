import { ArrowRight } from "@phosphor-icons/react";
import type { Stages } from "../../lib/api";
import { EmptyField, Panel } from "../Panel";

type Data = Stages["semantic_analysis"];

export function SemanticPanel({ data }: { data: Data }) {
  const types = Object.entries(data.resolved_types);

  return (
    <Panel title="Semantic analysis" note={`${data.tables.length} relations bound`}>
      <Field label="Relations">
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          {data.tables.map((t) => (
            <span key={t} className="font-mono text-[12.5px] text-paper">
              {t}
            </span>
          ))}
        </div>
      </Field>

      <Field label="Join plan">
        {data.join_plan.length === 0 ? (
          <p className="font-mono text-[12.5px] text-muted">
            single relation, no join required
          </p>
        ) : (
          <ul className="space-y-1.5">
            {data.join_plan.map((j, i) => (
              <li key={i} className="flex items-center gap-2 font-mono text-[12.5px]">
                <span className="text-paper">{j.left}</span>
                <ArrowRight size={11} className="text-signal" weight="bold" />
                <span className="text-paper">{j.right}</span>
                <span className="text-muted">on {j.on}</span>
              </li>
            ))}
          </ul>
        )}
      </Field>

      <Field label="Resolved types">
        <div className="grid grid-cols-1 gap-x-10 gap-y-1 sm:grid-cols-2">
          {types.map(([ref, type]) => (
            <div key={ref} className="flex items-baseline justify-between gap-4">
              <span className="truncate font-mono text-[12.5px] text-paper">{ref}</span>
              <span className="font-mono text-micro uppercase text-muted">{type}</span>
            </div>
          ))}
        </div>
      </Field>

      {data.warnings.length > 0 && (
        <Field label="Recovered">
          <ul className="space-y-1">
            {data.warnings.map((w, i) => (
              <li key={i} className="font-mono text-[12.5px] text-muted">
                {w.message}
              </li>
            ))}
          </ul>
        </Field>
      )}
    </Panel>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-rule/60 px-5 py-4 last:border-b-0">
      <p className="field-label mb-2">{label}</p>
      {children}
    </div>
  );
}

export { EmptyField };
