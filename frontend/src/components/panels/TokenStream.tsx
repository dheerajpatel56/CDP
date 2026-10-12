import { motion, useReducedMotion } from "framer-motion";
import type { Token } from "../../lib/api";
import { Panel } from "../Panel";

// Only tokens the compiler resolved against the schema get the accent. Everything
// else stays neutral, so the accent means "this bound to something real".
const RESOLVED = new Set(["TABLE", "COLUMN", "VALUE"]);
const STRUCTURAL = new Set(["AGGREGATE", "COMPARATOR", "LOGICAL", "ORDER", "GROUP", "LIMIT"]);

function tone(type: string) {
  if (RESOLVED.has(type)) return "text-signal";
  if (STRUCTURAL.has(type)) return "text-paper";
  if (type === "NUMBER" || type === "STRING") return "text-verify";
  return "text-muted";
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    // a catalog value carries [table, column, literal]; a column ref carries [table, column]
    const [table, column, literal] = value;
    return literal === undefined
      ? `${table}.${column}`
      : `${table}.${column} = ${typeof literal === "string" ? `'${literal}'` : literal}`;
  }
  return String(value);
}

export function TokenStream({ tokens, input }: { tokens: Token[]; input: string }) {
  const reduce = useReducedMotion();
  const visible = tokens.filter((t) => t.type !== "EOF");

  return (
    <Panel
      title="Token stream"
      note={`${visible.length} tokens, maximal munch`}
    >
      <div className="border-b border-rule px-5 py-4">
        <p className="field-label mb-2">Source</p>
        <p className="font-mono text-[13px] leading-relaxed text-paper/90">{input}</p>
      </div>

      <div className="divide-y divide-rule/60">
        {visible.map((t, i) => (
          <motion.div
            key={`${t.pos}-${i}`}
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.18, delay: Math.min(i * 0.012, 0.3) }}
            className="grid grid-cols-[2.5rem_7rem_1fr_1fr] items-baseline gap-3 px-5 py-1.5 hover:bg-ink-2"
          >
            <span className="tnum font-mono text-micro text-muted">
              {String(i).padStart(2, "0")}
            </span>
            <span className={`font-mono text-micro uppercase ${tone(t.type)}`}>
              {t.type}
            </span>
            <span className="truncate font-mono text-[12.5px] text-paper">{t.lexeme}</span>
            <span className="truncate font-mono text-[12.5px] text-muted">
              {renderValue(t.value)}
            </span>
          </motion.div>
        ))}
      </div>
    </Panel>
  );
}
