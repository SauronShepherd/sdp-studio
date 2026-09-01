import { useState } from "react";

type Run = { id: string; status?: string };

export function RunComparisonSelector({ runs, onCompare }: { runs: Run[]; onCompare: (left: string, right: string) => void }) {
  const [left, setLeft] = useState(runs[1]?.id || "");
  const [right, setRight] = useState(runs[0]?.id || "");
  if (runs.length < 2) return null;
  return <section aria-label="Run comparison controls">
    <label>Baseline run<select aria-label="Baseline run" value={left} onChange={(event) => setLeft(event.target.value)}>{runs.map((run) => <option value={run.id} key={`left-${run.id}`}>{run.id} · {run.status || "unknown"}</option>)}</select></label>
    <label>Current run<select aria-label="Current run" value={right} onChange={(event) => setRight(event.target.value)}>{runs.map((run) => <option value={run.id} key={`right-${run.id}`}>{run.id} · {run.status || "unknown"}</option>)}</select></label>
    <button className="preview" disabled={!left || !right || left === right} onClick={() => onCompare(left, right)}>Compare selected runs</button>
  </section>;
}
