import { Warning } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "./components/Panel";
import { PhaseRail, PhaseStrip } from "./components/PhaseRail";
import { QueryBar } from "./components/QueryBar";
import { AstTree } from "./components/panels/AstTree";
import { IrListing } from "./components/panels/IrListing";
import { OptimizerPanel } from "./components/panels/OptimizerPanel";
import { ResultsPanel } from "./components/panels/ResultsPanel";
import { SecurityPanel } from "./components/panels/SecurityPanel";
import { SemanticPanel } from "./components/panels/SemanticPanel";
import { SqlPanel } from "./components/panels/SqlPanel";
import { TokenStream } from "./components/panels/TokenStream";
import { api, PHASE_LABELS, type CompileResult, type PhaseKey } from "./lib/api";

export default function App() {
  const [result, setResult] = useState<CompileResult | null>(null);
  const [active, setActive] = useState<PhaseKey>("lexical_analysis");
  const [running, setRunning] = useState(false);
  const [fault, setFault] = useState<string | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [tables, setTables] = useState<Record<string, number>>({});
  const [backend, setBackend] = useState<string>("");

  useEffect(() => {
    api.examples().then((r) => setExamples(r.examples)).catch(() => undefined);
    api
      .health()
      .then((r) => {
        setTables(r.tables);
        setBackend(r.backend);
      })
      .catch(() => undefined);
  }, []);

  const compile = useCallback(async (text: string) => {
    setRunning(true);
    setFault(null);
    try {
      const r = await api.compile(text);
      setResult(r);
      setActive(
        r.failed_phase ? (r.failed_phase as PhaseKey) : r.execution ? "execution" : "code_generation",
      );
    } catch (e) {
      setResult(null);
      setFault(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, []);

  const totalRows = Object.values(tables).reduce((a, b) => a + b, 0);

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center justify-between border-b border-rule px-5 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="prose-sans text-[13px] font-medium tracking-tight text-paper">
            Natural Language Query Compiler
          </h1>
          <span className="hidden font-mono text-micro text-muted sm:inline">
            natural language to verified SQL
          </span>
        </div>
        {totalRows > 0 && (
          <span className="tnum font-mono text-micro text-muted">
            {backend && <span className="text-signal">{backend}</span>}
            {backend && " · "}
            {Object.keys(tables).length} relations, {totalRows.toLocaleString()} rows
          </span>
        )}
      </header>

      <QueryBar onSubmit={compile} running={running} examples={examples} />

      <PhaseStrip result={result} active={active} onSelect={setActive} />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[304px_1fr]">
        <aside className="hidden border-r border-rule lg:block">
          <PhaseRail
            result={result}
            active={active}
            onSelect={setActive}
            running={running}
          />
        </aside>

        <main className="min-h-0 overflow-hidden">
          {fault ? (
            <Fault message={fault} />
          ) : !result ? (
            <Idle />
          ) : (
            <PhaseView result={result} phase={active} />
          )}
        </main>
      </div>
    </div>
  );
}

function PhaseView({ result, phase }: { result: CompileResult; phase: PhaseKey }) {
  const s = result.stages;

  if (result.failed_phase === phase) {
    return <Blocked result={result} phase={phase} />;
  }

  switch (phase) {
    case "lexical_analysis":
      return s.lexical_analysis ? (
        <TokenStream
          tokens={s.lexical_analysis.tokens}
          input={s.lexical_analysis.input}
        />
      ) : null;

    case "syntax_analysis":
      return s.syntax_analysis ? (
        <AstTree
          tree={s.syntax_analysis.ast_tree}
          diagnostics={s.syntax_analysis.diagnostics}
        />
      ) : null;

    case "semantic_analysis":
      return s.semantic_analysis ? <SemanticPanel data={s.semantic_analysis} /> : null;

    case "intermediate_representation":
      return s.intermediate_representation ? (
        <IrListing
          listing={s.intermediate_representation.listing}
          opCount={s.intermediate_representation.op_count}
        />
      ) : null;

    case "optimization":
      return s.optimization && s.intermediate_representation ? (
        <OptimizerPanel
          before={s.intermediate_representation.listing}
          data={s.optimization}
        />
      ) : null;

    case "code_generation":
      return s.code_generation ? <SqlPanel data={s.code_generation} /> : null;

    case "security_analysis":
      return s.security_analysis ? <SecurityPanel data={s.security_analysis} /> : null;

    case "execution":
      return result.execution ? <ResultsPanel execution={result.execution} /> : null;

    default:
      return null;
  }
}

function Blocked({ result, phase }: { result: CompileResult; phase: PhaseKey }) {
  return (
    <Panel title={PHASE_LABELS[phase]} note="compilation stopped here">
      <div className="px-5 py-6">
        <div className="flex items-start gap-2.5">
          <Warning size={14} weight="fill" className="mt-[3px] shrink-0 text-fault" />
          <div className="min-w-0">
            {result.errors.map((e, i) => (
              <p key={i} className="prose-sans max-w-[72ch] text-[13px] leading-relaxed text-paper">
                {e.message}
              </p>
            ))}
            <p className="prose-sans mt-3 max-w-[72ch] text-[12.5px] leading-relaxed text-muted">
              Later phases did not run. The compiler refuses to emit a statement it
              cannot fully verify.
            </p>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function Idle() {
  return (
    <div className="flex h-full items-center px-5">
      <div className="max-w-[58ch]">
        <p className="prose-sans text-[15px] leading-relaxed text-paper/80">
          A question in English is compiled the way a program is: scanned into tokens,
          parsed to a syntax tree, checked against the schema, lowered to relational
          algebra, optimized, and emitted as SQL that is verified before it runs.
        </p>
        <p className="mt-3 font-mono text-[12.5px] text-muted">
          Press <span className="text-signal">/</span> to focus the query field.
        </p>
      </div>
    </div>
  );
}

function Fault({ message }: { message: string }) {
  return (
    <Panel title="Backend unreachable" note="compiler API did not respond">
      <div className="px-5 py-6">
        <p className="prose-sans max-w-[72ch] text-[13px] leading-relaxed text-paper">
          The frontend could not reach the compiler service.
        </p>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-[12.5px] text-fault">
          {message}
        </pre>
        <p className="mt-4 field-label mb-1.5">Start it with</p>
        <pre className="overflow-x-auto font-mono text-[12.5px] text-muted">
          cd backend{"\n"}.venv/Scripts/python.exe -m uvicorn main:app --port 8000
        </pre>
      </div>
    </Panel>
  );
}
