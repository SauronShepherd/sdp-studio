type OutlineNode = { id: string; label?: string; operatorId?: string };
type OutlineEdge = { source: string; target: string };

/** Keyboard- and screen-reader-friendly alternative to the spatial canvas. */
export function GraphOutline({ nodes, edges }: { nodes: OutlineNode[]; edges: OutlineEdge[] }) {
  if (nodes.length === 0) return <section aria-label="Pipeline outline"><p className="muted">No operators in the pipeline.</p></section>;
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target]);
  return <section aria-label="Pipeline outline"><h3>Pipeline outline</h3><ol>{nodes.map((node) => <li key={node.id}><strong>{node.label || node.operatorId || "Operator"}</strong><small>{node.operatorId || "custom"}</small>{(outgoing.get(node.id) || []).length > 0 && <span> → {(outgoing.get(node.id) || []).map((target) => nodes.find((candidate) => candidate.id === target)?.label || target).join(", ")}</span>}</li>)}</ol></section>;
}
