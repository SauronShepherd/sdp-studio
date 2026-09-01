export type LayoutItem = { id: string; position: { x: number; y: number } };
export type LayoutEdge = { source: string; target: string };

export function calculateGridLayout<T extends LayoutItem>(nodes: T[], edges: LayoutEdge[] = []): T[] {
  if (edges.length === 0) {
    const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
    return nodes.map((node, index) => ({ ...node, position: { x: 80 + (index % columns) * 240, y: 80 + Math.floor(index / columns) * 150 } }));
  }
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(nodes.map((node) => [node.id, [] as string[]]));
  for (const edge of edges) {
    if (indegree.has(edge.target) && outgoing.has(edge.source)) {
      indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
      outgoing.get(edge.source)?.push(edge.target);
    }
  }
  const layers = new Map<string, number>();
  const queue = nodes.filter((node) => (indegree.get(node.id) || 0) === 0).map((node) => node.id).sort();
  queue.forEach((id) => layers.set(id, 0));
  for (let index = 0; index < queue.length; index += 1) {
    const id = queue[index];
    for (const child of (outgoing.get(id) || []).sort()) {
      layers.set(child, Math.max(layers.get(child) || 0, (layers.get(id) || 0) + 1));
      const count = (indegree.get(child) || 0) - 1;
      indegree.set(child, count);
      if (count === 0) queue.push(child);
    }
  }
  const rows = new Map<number, string[]>();
  nodes.forEach((node, index) => { const layer = layers.get(node.id) ?? index; rows.set(layer, [...(rows.get(layer) || []), node.id]); });
  return nodes.map((node, index) => {
    const layer = layers.get(node.id) ?? index;
    const row = (rows.get(layer) || []).indexOf(node.id);
    return { ...node, position: { x: 80 + layer * 260, y: 80 + Math.max(0, row) * 150 } };
  });
}

export function layoutInWorker<T extends LayoutItem>(nodes: T[], edges: LayoutEdge[] = []): Promise<T[]> {
  if (typeof Worker === "undefined") return Promise.resolve(calculateGridLayout(nodes, edges));
  return new Promise((resolve) => {
    const worker = new Worker(new URL("./layout.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<T[]>) => { worker.terminate(); resolve(event.data); };
    worker.onerror = () => { worker.terminate(); resolve(calculateGridLayout(nodes, edges)); };
    worker.postMessage({ nodes, edges });
  });
}
