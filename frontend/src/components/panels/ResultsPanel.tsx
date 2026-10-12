import type { Execution } from "../../lib/api";
import { Panel } from "../Panel";

function isNumeric(v: unknown): v is number {
  return typeof v === "number";
}

export function ResultsPanel({ execution }: { execution: Execution }) {
  const { columns, rows } = execution;

  // a column is numeric when its first non-null value is a number
  const numericColumns = new Set(
    columns.filter((c) => {
      const sample = rows.find((r) => r[c] !== null && r[c] !== undefined);
      return sample ? isNumeric(sample[c]) : false;
    }),
  );

  return (
    <Panel
      title="Results"
      note={`${execution.row_count} rows in ${execution.duration_ms.toFixed(2)} ms`}
    >
      {rows.length === 0 ? (
        <div className="px-5 py-10">
          <p className="prose-sans text-[13px] text-paper">No rows matched.</p>
          <p className="prose-sans mt-1.5 max-w-[60ch] text-[12.5px] leading-relaxed text-muted">
            The statement compiled and ran. The predicate is simply satisfied by
            nothing in the current data.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-rule">
                {columns.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className={[
                      "whitespace-nowrap px-5 py-2.5 font-mono text-micro uppercase text-muted",
                      numericColumns.has(c) ? "text-right" : "text-left",
                    ].join(" ")}
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-rule/40 hover:bg-ink-2">
                  {columns.map((c) => {
                    const v = row[c];
                    return (
                      <td
                        key={c}
                        className={[
                          "whitespace-nowrap px-5 py-1.5 font-mono text-[12.5px]",
                          isNumeric(v) ? "tnum text-right text-verify" : "text-paper/90",
                        ].join(" ")}
                      >
                        {v === null ? <span className="text-rule">null</span> : String(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {execution.truncated && (
        <p className="border-t border-rule px-5 py-3 font-mono text-micro text-signal">
          Output truncated at the row cap.
        </p>
      )}

      {execution.engine_plan && execution.engine_plan.length > 0 && (
        <div className="border-t border-rule px-5 py-4">
          <p className="field-label mb-2">Engine plan</p>
          <div className="space-y-0.5">
            {execution.engine_plan.map((p, i) => (
              <p key={i} className="font-mono text-[12.5px] text-muted">
                {p.detail}
              </p>
            ))}
          </div>
          <p className="prose-sans mt-3 max-w-[70ch] text-[12.5px] leading-relaxed text-muted">
            What the database actually did, next to what the compiler planned.
          </p>
        </div>
      )}
    </Panel>
  );
}
