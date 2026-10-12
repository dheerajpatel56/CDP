import { Panel } from "../Panel";

const OPCODES = new Set([
  "SCAN", "JOIN", "FILTER", "PROJECT", "AGGREGATE", "SORT", "RANK", "LIMIT",
]);

/**
 * Highlights the three-address shape: destination temporary, opcode, operands.
 * Everything else stays muted so the data flow between temporaries is readable
 * at a glance. One operation per line, never wrapped.
 */
export function IrLine({ line, changed }: { line: string; changed?: boolean }) {
  const parts = line.split(" ");

  return (
    <div
      className={[
        "flex gap-2 whitespace-pre px-5 py-[3px] font-mono text-[12.5px] leading-snug",
        changed ? "bg-signal/[0.07]" : "",
      ].join(" ")}
    >
      <span
        aria-hidden
        className={changed ? "shrink-0 text-signal" : "shrink-0 text-transparent"}
      >
        |
      </span>
      <span>
        {parts.map((p, i) => {
          let cls = "text-muted";
          if (/^t\d+,?$/.test(p)) cls = "text-paper";
          else if (OPCODES.has(p)) cls = "text-signal";
          else if (p === "=") cls = "text-rule";
          return (
            <span key={i} className={cls}>
              {p}
              {i < parts.length - 1 ? " " : ""}
            </span>
          );
        })}
      </span>
    </div>
  );
}

export function IrListing({
  listing,
  opCount,
}: {
  listing: string;
  opCount: number;
}) {
  const lines = listing.split("\n").filter(Boolean);

  return (
    <Panel
      title="Intermediate representation"
      note={`${opCount} operations, three address form`}
    >
      <div className="overflow-x-auto py-3">
        {lines.map((line, i) => (
          <IrLine key={i} line={line} />
        ))}
      </div>
      <div className="border-t border-rule px-5 py-4">
        <p className="prose-sans max-w-[70ch] text-[12.5px] leading-relaxed text-muted">
          Each instruction writes one temporary and reads temporaries produced
          earlier. The optimizer rewrites this listing, not the SQL text.
        </p>
      </div>
    </Panel>
  );
}
