"""FastAPI surface for the Natural Language Query Compiler.

Every endpoint returns the full phase-by-phase compilation so the frontend can
render the pipeline, not just the final answer.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from compiler.pipeline import PHASES, QueryCompiler
from compiler.schema import DEMO_SCHEMA
from db.config import ACTIVE
from db.executor import ExecutionError, execute, explain, table_stats

app = FastAPI(
    title="Natural Language Query Compiler",
    description="Compiles natural language into verified, optimized SQL.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

compiler = QueryCompiler(DEMO_SCHEMA)  # dialect follows DATABASE_URL


class CompileRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500,
                      description="Natural language question")
    execute: bool = Field(True, description="Run the generated SQL against the demo DB")


EXAMPLES = [
    "Show the top 5 students from each department who scored above 85",
    "Find students from Mumbai with marks between 70 and 90",
    "students not from Mumbai",
    "students admitted last year",
    "students who joined after 2022",
    "departments with more than 20 students",
    "What is the average marks of students in each department",
    "youngest 5 students",
    "students whose marks are greater than age",
    "list distinct cities",
]


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "phases": PHASES,
        "backend": ACTIVE.name,
        "tables": table_stats(),
    }


@app.get("/api/schema")
def get_schema():
    return {
        "tables": [
            {
                "name": t.name,
                "synonyms": t.synonyms,
                "columns": [{"name": c.name, "type": c.type, "synonyms": c.synonyms}
                            for c in t.columns],
            }
            for t in DEMO_SCHEMA.tables.values()
        ],
        "foreign_keys": [
            {"from": "%s.%s" % (fk.from_table, fk.from_column),
             "to": "%s.%s" % (fk.to_table, fk.to_column)}
            for fk in DEMO_SCHEMA.foreign_keys
        ],
    }


@app.get("/api/examples")
def examples():
    return {"examples": EXAMPLES}


@app.post("/api/compile")
def compile_query(req: CompileRequest):
    result = compiler.compile(req.text)
    payload = result.to_dict()

    if not result.ok:
        payload["execution"] = None
        return payload

    if req.execute:
        try:
            payload["execution"] = execute(result.sql, result.params)
            payload["execution"]["engine_plan"] = explain(result.sql, result.params)
        except ExecutionError as e:
            raise HTTPException(status_code=400,
                                detail="execution failed: %s" % e)
    else:
        payload["execution"] = None

    return payload


@app.post("/api/explain")
def explain_query(req: CompileRequest):
    """Compile without executing - plan and SQL only."""
    result = compiler.compile(req.text)
    if not result.ok:
        return result.to_dict()
    return {
        "sql": result.sql,
        "params": result.params,
        "compiler_plan": result.stages["optimization"]["listing"],
        "transformations": result.stages["optimization"]["transformations"],
        "engine_plan": explain(result.sql, result.params),
    }
