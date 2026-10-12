import { ArrowRight, CircleNotch } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

interface Props {
  onSubmit: (text: string) => void;
  running: boolean;
  examples: string[];
}

export function QueryBar({ onSubmit, running, examples }: Props) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(value: string) {
    const v = value.trim();
    if (!v || running) return;
    setText(v);
    onSubmit(v);
  }

  return (
    <div className="border-b border-rule">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
        className="flex items-center gap-3 px-5 py-3"
      >
        <label htmlFor="nlq" className="field-label shrink-0">
          Query
        </label>
        <input
          id="nlq"
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask in plain English, then press Enter"
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent font-mono text-[13.5px] text-paper placeholder:text-muted/70 focus:outline-none"
        />
        <kbd className="hidden shrink-0 border border-rule px-1.5 py-0.5 font-mono text-micro text-muted sm:block">
          /
        </kbd>
        <button
          type="submit"
          disabled={running || !text.trim()}
          className="flex shrink-0 items-center gap-1.5 border border-rule px-3 py-1.5 font-mono text-micro uppercase text-paper transition-colors hover:border-signal hover:text-signal disabled:cursor-not-allowed disabled:border-rule disabled:text-muted/50 active:translate-y-[1px]"
        >
          {running ? (
            <>
              <CircleNotch size={11} weight="bold" className="animate-spin" />
              Compiling
            </>
          ) : (
            <>
              Compile
              <ArrowRight size={11} weight="bold" />
            </>
          )}
        </button>
      </form>

      {examples.length > 0 && (
        <div className="flex items-center gap-4 overflow-x-auto border-t border-rule/50 px-5 py-2">
          <span className="field-label shrink-0">Try</span>
          {examples.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => submit(ex)}
              disabled={running}
              className="shrink-0 whitespace-nowrap font-mono text-[12px] text-muted transition-colors hover:text-signal disabled:opacity-50"
            >
              {ex}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
