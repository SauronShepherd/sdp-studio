import { useMemo, useState } from "react";

type PlanNode = { id?: string; operator?: string; phase?: string; depth?: number; raw?: string };
type PlanOperation = { op: string; index: number; before?: PlanNode; after?: PlanNode; node?: PlanNode };

export function PlanInspector({ value }: { value: string }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"tree" | "text">("tree");
  const parsed = useMemo(() => { try { return JSON.parse(value) as { nodes?: PlanNode[]; diff?: { operations?: PlanOperation[] } }; } catch { return null; } }, [value]);
  const nodes = (parsed?.nodes || []).filter((node) => `${node.operator || ""} ${node.phase || ""} ${node.raw || ""}`.toLowerCase().includes(query.toLowerCase()));
  const controls = <div className="debug-controls"><button className="preview" onClick={() => setMode("tree")}>Tree</button><button className="preview" onClick={() => setMode("text")}>Text</button><input aria-label="Search plan" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search plan" /></div>;
  if (mode === "text" || !parsed?.nodes) return <section aria-label="Plan inspector">{controls}<pre className="generated">{value}</pre></section>;
  return <section aria-label="Plan inspector">{controls}{parsed.diff?.operations && <section aria-label="Plan diff"><h3>Structural changes</h3><ul>{parsed.diff.operations.map((operation, index) => <li key={`${operation.op}-${operation.index}-${index}`}><strong>{operation.op}</strong> at {operation.index}: {operation.before?.operator || operation.after?.operator || operation.node?.operator || "node"}</li>)}</ul></section>}<ol className="plan-tree">{nodes.map((node, index) => <li key={node.id || index} style={{ marginLeft: `${Math.min(node.depth || 0, 12) * 8}px` }}><strong>{node.operator || "Unknown"}</strong> <small>{node.phase || "unknown"}</small></li>)}</ol></section>;
}
