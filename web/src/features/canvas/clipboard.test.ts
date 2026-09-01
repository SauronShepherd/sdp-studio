import type { Node } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { cloneNodeForPaste } from "./clipboard";

describe("cloneNodeForPaste", () => {
  it("creates a deterministic offset clone without mutating the source", () => {
    const source = { id: "filter", position: { x: 10, y: 20 }, data: { operatorId: "transform.filter" } } as Node;
    const clone = cloneNodeForPaste(source, new Set(["filter", "filter-copy"]));
    expect(clone.id).toBe("filter-copy-2");
    expect(clone.position).toEqual({ x: 42, y: 52 });
    expect(clone.data).toEqual(source.data);
    expect(source.position).toEqual({ x: 10, y: 20 });
  });
});
