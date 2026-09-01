import { describe, expect, it } from "vitest";
import { calculateGridLayout } from "./layout";

describe("canvas layout", () => {
  it("is deterministic and preserves node identities", () => {
    const result = calculateGridLayout([{ id: "a", position: { x: 0, y: 0 } }, { id: "b", position: { x: 0, y: 0 } }]);
    expect(result.map((node) => [node.id, node.position])).toEqual([["a", { x: 80, y: 80 }], ["b", { x: 320, y: 80 }]]);
  });

  it("uses graph topology for layered placement", () => {
    const result = calculateGridLayout(
      [{ id: "output", position: { x: 0, y: 0 } }, { id: "source", position: { x: 0, y: 0 } }, { id: "filter", position: { x: 0, y: 0 } }],
      [{ source: "source", target: "filter" }, { source: "filter", target: "output" }],
    );
    expect(result.find((node) => node.id === "source")?.position.x).toBe(80);
    expect(result.find((node) => node.id === "filter")?.position.x).toBe(340);
    expect(result.find((node) => node.id === "output")?.position.x).toBe(600);
  });
});
