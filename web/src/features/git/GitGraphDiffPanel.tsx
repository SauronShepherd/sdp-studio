import { useState } from "react";
import { api } from "../../api";

export function GitGraphDiffPanel({ projectId }: { projectId: string | null }) {
  const [left, setLeft] = useState("HEAD~1");
  const [right, setRight] = useState("HEAD");
  const [result, setResult] = useState<{ summary: Record<string, number>; changed_nodes: unknown[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const compare = async () => {
    if (!projectId) return;
    try { setError(null); setResult((await api.gitGraphDiff(projectId, left, right)).diff); }
    catch (cause: unknown) { setError(cause instanceof Error ? cause.message : "Graph diff failed"); }
  };
  return <section id="workspace-view-diff" className="git-graph-diff" aria-label="Git graph diff"><h3>Visual Git diff</h3><label>Base<input aria-label="Base Git ref" value={left} onChange={(event) => setLeft(event.target.value)} /></label><label>Compare<input aria-label="Compare Git ref" value={right} onChange={(event) => setRight(event.target.value)} /></label><button className="preview" onClick={() => void compare()} disabled={!projectId}>Compare graph</button>{error && <p role="alert">{error}</p>}{result && <div role="status"><strong>{result.changed_nodes.length} changed nodes</strong><small>{Object.entries(result.summary).map(([key, count]) => `${key}: ${count}`).join(" · ")}</small></div>}</section>;
}
