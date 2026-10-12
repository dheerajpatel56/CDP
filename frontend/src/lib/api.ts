export type Severity = "error" | "warning" | "pass";

export interface Token {
  type: string;
  lexeme: string;
  value: unknown;
  pos: number;
  line: number;
}

export interface TreeNode {
  name: string;
  children: TreeNode[];
}

export interface IROp {
  kind: string;
  dest: string;
  args: string[];
  [key: string]: unknown;
}

export interface Transformation {
  rule: string;
  detail: string;
}

export interface Diagnostic {
  severity: Severity;
  message: string;
  lexeme?: string;
  pos?: number;
  phase?: string;
}

export interface Stages {
  lexical_analysis: {
    input: string;
    tokens: Token[];
    token_count: number;
    duration_ms: number;
  };
  syntax_analysis: {
    ast: Record<string, unknown>;
    ast_tree: TreeNode;
    diagnostics: Diagnostic[];
    duration_ms: number;
  };
  semantic_analysis: {
    join_plan: { left: string; right: string; on: string }[];
    tables: string[];
    warnings: Diagnostic[];
    resolved_types: Record<string, string>;
    duration_ms: number;
  };
  intermediate_representation: {
    ops: IROp[];
    listing: string;
    op_count: number;
    duration_ms: number;
  };
  optimization: {
    ops: IROp[];
    listing: string;
    transformations: Transformation[];
    ops_before: number;
    ops_after: number;
    duration_ms: number;
  };
  code_generation: {
    sql: string;
    params: unknown[];
    preview: string;
    dialect: string;
    duration_ms: number;
  };
  security_analysis: {
    safe: boolean;
    findings: Diagnostic[];
    tables_accessed: string[];
    parameter_count: number;
    join_count: number;
    row_cap: number;
    duration_ms: number;
  };
  total_duration_ms?: number;
}

export interface Execution {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  engine_plan?: { detail?: string }[];
}

export interface CompileResult {
  ok: boolean;
  failed_phase: string | null;
  sql: string | null;
  params: unknown[];
  errors: Diagnostic[];
  warnings: Diagnostic[];
  stages: Partial<Stages>;
  execution: Execution | null;
}

export interface SchemaTable {
  name: string;
  synonyms: string[];
  columns: { name: string; type: string; synonyms: string[] }[];
}

export interface SchemaInfo {
  tables: SchemaTable[];
  foreign_keys: { from: string; to: string }[];
}

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  compile: (text: string) =>
    request<CompileResult>("/compile", {
      method: "POST",
      body: JSON.stringify({ text, execute: true }),
    }),
  schema: () => request<SchemaInfo>("/schema"),
  examples: () => request<{ examples: string[] }>("/examples"),
  health: () =>
    request<{
      status: string;
      phases: string[];
      backend: string;
      tables: Record<string, number>;
    }>("/health"),
};

export const PHASE_LABELS: Record<string, string> = {
  lexical_analysis: "Lexical analysis",
  syntax_analysis: "Syntax analysis",
  semantic_analysis: "Semantic analysis",
  intermediate_representation: "Intermediate representation",
  optimization: "Optimization",
  code_generation: "Code generation",
  security_analysis: "Security analysis",
  execution: "Execution",
};

export const PHASE_SUBTITLES: Record<string, string> = {
  lexical_analysis: "Tokenizer",
  syntax_analysis: "Parser, AST",
  semantic_analysis: "Symbol table, joins",
  intermediate_representation: "Three address code",
  optimization: "Plan rewriting",
  code_generation: "SQL emission",
  security_analysis: "Static analysis gate",
  execution: "Runtime",
};

export const PHASE_ORDER = [
  "lexical_analysis",
  "syntax_analysis",
  "semantic_analysis",
  "intermediate_representation",
  "optimization",
  "code_generation",
  "security_analysis",
  "execution",
] as const;

export type PhaseKey = (typeof PHASE_ORDER)[number];
