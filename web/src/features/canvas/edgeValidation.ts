export type CanvasOperator = { id: string; inputs?: string[]; outputs?: string[]; modes?: string[] };
export type CanvasNode = { id: string; type: string; config?: Record<string, unknown> };
export type CanvasEdge = { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null };

export function validateConnection(
  connection: { source?: string | null; target?: string | null; sourceHandle?: string | null; targetHandle?: string | null },
  nodes: CanvasNode[], edges: CanvasEdge[], operators: CanvasOperator[],
): string | null {
  if (!connection.source || !connection.target || connection.source === connection.target) return "A node cannot connect to itself";
  if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target && edge.targetHandle === connection.targetHandle)) return "That connection already exists";
  const source = nodes.find((node) => node.id === connection.source);
  const target = nodes.find((node) => node.id === connection.target);
  const sourceOperator = operators.find((operator) => operator.id === source?.type);
  const targetOperator = operators.find((operator) => operator.id === target?.type);
  const sourcePort = connection.sourceHandle || "out";
  const targetPort = connection.targetHandle || "in";
  if (!source || !target || !sourceOperator?.outputs?.includes(sourcePort)) return `Unknown output port: ${sourcePort}`;
  const adjacency = new Map(nodes.map((node) => [node.id, [] as string[]]));
  for (const edge of edges) adjacency.get(edge.source)?.push(edge.target);
  adjacency.get(source.id)?.push(target.id);
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const hasCycle = (id: string): boolean => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    if ((adjacency.get(id) || []).some(hasCycle)) return true;
    visiting.delete(id); visited.add(id); return false;
  };
  if (nodes.some((node) => hasCycle(node.id))) return "Connection would create a cycle";
  if (!targetOperator?.inputs?.includes(targetPort)) return `Unknown input port: ${targetPort}`;
  if (edges.some((edge) => edge.target === target.id && (edge.targetHandle || "in") === targetPort)) return `Input already connected: ${targetPort}`;
  const streaming = Boolean(source.config?.streaming) || source.type === "source.kafka";
  if (streaming && !(targetOperator?.modes || ["batch", "streaming"]).includes("streaming")) return "Streaming input is incompatible with this operator";
  return null;
}
