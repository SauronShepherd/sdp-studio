import type { Node } from "@xyflow/react";

export function cloneNodeForPaste(node: Node, existingIds: ReadonlySet<string>): Node {
  const base = `${node.id}-copy`;
  let id = base;
  let index = 2;
  while (existingIds.has(id)) id = `${base}-${index++}`;
  return {
    ...node,
    id,
    position: { x: node.position.x + 32, y: node.position.y + 32 },
    selected: true,
    data: { ...node.data },
  };
}
