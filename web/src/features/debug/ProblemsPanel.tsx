import { useMemo, useState } from "react";
import type { CapabilityProblem } from "../../api";

type Props = { problems: CapabilityProblem[]; onSelectNode: (nodeId: string) => void };

export function ProblemsPanel({ problems, onSelectNode }: Props) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return problems;
    return problems.filter((problem) => [problem.code, problem.severity, problem.message, problem.node_id].some((value) => String(value || "").toLowerCase().includes(normalized)));
  }, [problems, query]);
  if (problems.length === 0) return null;
  return <section className="problems-panel" aria-label="Problems"><h2>Problems</h2><label>Filter problems<input aria-label="Filter problems" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="code, severity, or message" /></label>{filtered.length === 0 ? <p className="muted">No matching problems.</p> : filtered.map((problem, index) => <article className="problem-item" key={`${problem.code}-${problem.node_id || index}`}><button className="problem-select" onClick={() => problem.node_id && onSelectNode(problem.node_id)} disabled={!problem.node_id}><span>{problem.severity}</span><strong>{problem.code}</strong><small>{problem.message}</small>{problem.line != null && <small>Line {problem.line}</small>}</button>{problem.doc_link && <a href={problem.doc_link} target="_blank" rel="noreferrer">Documentation</a>}</article>)}</section>;
}
