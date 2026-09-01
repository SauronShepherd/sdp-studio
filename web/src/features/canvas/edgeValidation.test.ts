import { describe, expect, it } from "vitest";
import { validateConnection } from "./edgeValidation";

const operators = [
  { id: "source.table", outputs: ["out"], modes: ["batch", "streaming"] },
  { id: "transform.filter", inputs: ["in"], outputs: ["out"], modes: ["batch", "streaming"] },
  { id: "utility.note", inputs: [], outputs: [], modes: ["batch"] },
];

describe("validateConnection", () => {
  it("rejects unknown ports, duplicate inputs, and cycles", () => {
    const nodes = [{ id: "source", type: "source.table" }, { id: "filter", type: "transform.filter" }];
    expect(validateConnection({ source: "source", target: "filter", sourceHandle: "bad" }, nodes, [], operators)).toContain("Unknown output");
    const edge = { source: "source", target: "filter", targetHandle: "in" };
    expect(validateConnection({ source: "source", target: "filter" }, nodes, [edge], operators)).toContain("already connected");
    expect(validateConnection({ source: "filter", target: "source" }, nodes, [edge], operators)).toContain("cycle");
  });
});
