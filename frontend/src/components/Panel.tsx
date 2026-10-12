import type { ReactNode } from "react";

interface Props {
  title: string;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

/**
 * The single structural unit of the workspace: a titled field of compiler output.
 * No card chrome, no elevation. A hairline rule carries the hierarchy.
 */
export function Panel({ title, note, actions, children }: Props) {
  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-rule px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h2 className="prose-sans text-[13px] font-medium text-paper">{title}</h2>
          {note && <span className="font-mono text-micro text-muted">{note}</span>}
        </div>
        {actions}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

export function EmptyField({ children }: { children: ReactNode }) {
  return (
    <div className="px-5 py-8">
      <p className="font-mono text-[12.5px] text-muted">{children}</p>
    </div>
  );
}
