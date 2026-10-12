import Editor from "@monaco-editor/react";
import { Check, Copy } from "@phosphor-icons/react";
import { useState } from "react";
import type { Stages } from "../../lib/api";
import { Panel } from "../Panel";

export function SqlPanel({ data }: { data: Stages["code_generation"] }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(data.sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const lineCount = data.sql.split("\n").length;

  return (
    <Panel
      title="Generated SQL"
      note={`${data.dialect}, ${data.params.length} bound parameters`}
      actions={
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 border border-rule px-2.5 py-1 font-mono text-micro uppercase text-muted transition-colors hover:border-muted hover:text-paper active:translate-y-[1px]"
        >
          {copied ? <Check size={11} weight="bold" /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      }
    >
      <div className="border-b border-rule" style={{ height: Math.min(lineCount * 19 + 24, 420) }}>
        <Editor
          language="sql"
          value={data.sql}
          theme="nlq-dark"
          options={{
            readOnly: true,
            domReadOnly: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
            lineNumbers: "on",
            lineNumbersMinChars: 3,
            renderLineHighlight: "none",
            scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
            padding: { top: 12, bottom: 12 },
            overviewRulerLanes: 0,
            folding: false,
            contextmenu: false,
          }}
          beforeMount={(monaco) => {
            monaco.editor.defineTheme("nlq-dark", {
              base: "vs-dark",
              inherit: true,
              rules: [
                { token: "", foreground: "e8e6e1" },
                { token: "keyword", foreground: "d8763a" },
                { token: "keyword.sql", foreground: "d8763a" },
                // aggregate and window functions are keywords here, not a third colour
                { token: "predefined", foreground: "d8763a" },
                { token: "predefined.sql", foreground: "d8763a" },
                { token: "string", foreground: "5f8f6a" },
                { token: "string.sql", foreground: "5f8f6a" },
                { token: "number", foreground: "5f8f6a" },
                { token: "number.sql", foreground: "5f8f6a" },
                { token: "operator", foreground: "8a8a94" },
                { token: "operator.sql", foreground: "8a8a94" },
                { token: "delimiter", foreground: "8a8a94" },
                { token: "delimiter.parenthesis", foreground: "8a8a94" },
                { token: "identifier", foreground: "e8e6e1" },
                { token: "identifier.sql", foreground: "e8e6e1" },
                { token: "comment", foreground: "8a8a94", fontStyle: "italic" },
              ],
              colors: {
                "editor.background": "#0d0d0f",
                "editor.foreground": "#e8e6e1",
                "editorLineNumber.foreground": "#2a2a31",
                "editorLineNumber.activeForeground": "#8a8a94",
                "editorGutter.background": "#0d0d0f",
              },
            });
          }}
        />
      </div>

      <div className="px-5 py-4">
        <p className="field-label mb-2">Bound parameters</p>
        {data.params.length === 0 ? (
          <p className="font-mono text-[12.5px] text-muted">none</p>
        ) : (
          <div className="flex flex-wrap gap-x-6 gap-y-1">
            {data.params.map((p, i) => (
              <span key={i} className="font-mono text-[12.5px]">
                <span className="text-muted">${i + 1}</span>{" "}
                <span className="text-verify">
                  {typeof p === "string" ? `'${p}'` : String(p)}
                </span>
              </span>
            ))}
          </div>
        )}
        <p className="prose-sans mt-3 max-w-[70ch] text-[12.5px] leading-relaxed text-muted">
          Literals are never written into the statement text. Code generation emits a
          placeholder and binds the value separately, so the generated SQL has no
          position an injected string could occupy.
        </p>
      </div>
    </Panel>
  );
}
