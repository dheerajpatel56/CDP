import type { Stages } from "../../lib/api";
import { Panel } from "../Panel";
import { IrLine } from "./IrListing";

interface Props {
  before: string;
  data: Stages["optimization"];
}

/**
 * An operation's identity is its destination and opcode. Attributes appended by
 * a rewrite (COLUMNS after projection pruning) are not identity changes, so the
 * diff marks only operations the optimizer actually moved, added, or retargeted.
 */
function identity(line: string): string {
  const [dest, , kind, ...rest] = line.split(" ");
  return [dest, kind, rest[0] ?? ""].join(" ");
}

export function OptimizerPanel({ before, data }: Props) {
  const beforeLines = before.split("\n").filter(Boolean);
  const afterLines = data.listing.split("\n").filter(Boolean);
  const removed = data.ops_before - data.ops_after;

  const beforeIndex = new Map(beforeLines.map((l, i) => [identity(l), i]));
  const changedAt = (line: string, i: number) => {
    const was = beforeIndex.get(identity(line));
    return was === undefined || was !== i;
  };

  return (
    <Panel
      title="Optimization"
      note={`${data.transformations.length} rewrites, ${data.ops_before} to ${data.ops_after} operations`}
    >
      <div className="border-b border-rule px-5 py-4">
        <p className="field-label mb-3">Transformations applied</p>
        {data.transformations.length === 0 ? (
          <p className="font-mono text-[12.5px] text-muted">
            plan already minimal, nothing to rewrite
          </p>
        ) : (
          <ol className="space-y-2.5">
            {data.transformations.map((t, i) => (
              <li key={i} className="flex gap-3">
                <span className="tnum mt-[2px] shrink-0 font-mono text-micro text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-[12.5px] text-signal">{t.rule}</p>
                  <p className="prose-sans mt-0.5 max-w-[72ch] text-[12.5px] leading-relaxed text-muted">
                    {t.detail}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2">
        <div className="border-b border-rule lg:border-b-0 lg:border-r">
          <p className="field-label px-5 pb-2 pt-4">Before</p>
          <div className="overflow-x-auto pb-4">
            {beforeLines.map((line, i) => (
              <IrLine key={i} line={line} />
            ))}
          </div>
        </div>
        <div>
          <p className="field-label px-5 pb-2 pt-4">
            After{removed > 0 ? ` · ${removed} fewer operations` : ""}
          </p>
          <div className="overflow-x-auto pb-4">
            {afterLines.map((line, i) => (
              <IrLine key={i} line={line} changed={changedAt(line, i)} />
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}
