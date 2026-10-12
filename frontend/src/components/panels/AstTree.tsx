import type { Diagnostic, TreeNode } from "../../lib/api";
import { Panel } from "../Panel";

/**
 * Rendered as an indented listing with box-drawing guides rather than a floating
 * node graph. A parse tree is a listing; drawing it as one keeps the structure
 * readable at depth and matches how the compiler itself prints it.
 */
function Row({
  node,
  prefix,
  isLast,
  depth,
}: {
  node: TreeNode;
  prefix: string;
  isLast: boolean;
  depth: number;
}) {
  const [label, detail] = splitLabel(node.name);
  const connector = depth === 0 ? "" : isLast ? "└─ " : "├─ ";
  const childPrefix = depth === 0 ? "" : prefix + (isLast ? "   " : "│  ");

  return (
    <>
      <div className="whitespace-pre px-5 py-[3px] font-mono text-[12.5px] leading-snug hover:bg-ink-2">
        <span className="text-rule">{prefix + connector}</span>
        <span className={depth === 0 ? "text-signal" : "text-paper"}>{label}</span>
        {detail && <span className="text-muted">{detail}</span>}
      </div>
      {node.children.map((child, i) => (
        <Row
          key={i}
          node={child}
          prefix={childPrefix}
          isLast={i === node.children.length - 1}
          depth={depth + 1}
        />
      ))}
    </>
  );
}

function splitLabel(name: string): [string, string] {
  const i = name.indexOf(" (");
  if (i === -1) return [name, ""];
  return [name.slice(0, i), name.slice(i)];
}

export function AstTree({
  tree,
  diagnostics,
}: {
  tree: TreeNode;
  diagnostics: Diagnostic[];
}) {
  const nodes = countNodes(tree);
  return (
    <Panel title="Abstract syntax tree" note={`${nodes} nodes`}>
      <div className="py-3">
        <Row node={tree} prefix="" isLast depth={0} />
      </div>

      {diagnostics.length > 0 && (
        <div className="border-t border-rule px-5 py-4">
          <p className="field-label mb-2">Parser diagnostics</p>
          <ul className="space-y-1">
            {diagnostics.map((d, i) => (
              <li key={i} className="font-mono text-[12.5px] text-muted">
                <span className="text-signal">{d.lexeme}</span> {d.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function countNodes(node: TreeNode): number {
  return 1 + node.children.reduce((n, c) => n + countNodes(c), 0);
}
