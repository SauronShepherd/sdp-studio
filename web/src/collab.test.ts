import { describe, expect, it } from "vitest";
import * as Y from "yjs";
import { collaborationWebSocketUrl, createPipelineDoc, decodeUpdate, encodeUpdate, persistOfflineState, projectFileText, readPipelineDoc, restoreOfflineState, setPipelineDoc, setProjectFileText, setSourceText, sourceText } from "./collab";

describe("Yjs pipeline collaboration", () => {
  it("round-trips a pipeline through a binary update", () => {
    const first = createPipelineDoc();
    const updates: Uint8Array[] = [];
    first.on("update", (update) => updates.push(update));
    const pipeline = { nodes: [], edges: [] };
    setPipelineDoc(first, pipeline);
    const second = createPipelineDoc();
    Y.applyUpdate(second, decodeUpdate(encodeUpdate(updates[0])));
    expect(readPipelineDoc(second)).toEqual(pipeline);
  });

  it("merges concurrent node edits from independent clients", () => {
    const first = createPipelineDoc();
    const second = createPipelineDoc();
    setPipelineDoc(first, { nodes: [{ id: "a", type: "source.table", position: { x: 0, y: 0 }, config: {} }], edges: [] });
    setPipelineDoc(second, { nodes: [{ id: "b", type: "source.table", position: { x: 1, y: 1 }, config: {} }], edges: [] });
    const merged = createPipelineDoc();
    Y.applyUpdate(merged, Y.encodeStateAsUpdate(first));
    Y.applyUpdate(merged, Y.encodeStateAsUpdate(second));
    expect(readPipelineDoc(merged)?.nodes.map((node) => node.id).sort()).toEqual(["a", "b"]);
  });

  it("preserves concurrent edits to different fields of one node", () => {
    const base = createPipelineDoc({ nodes: [{ id: "a", type: "source.table", position: { x: 0, y: 0 }, config: { table: "orders" } }], edges: [] });
    const left = createPipelineDoc();
    const right = createPipelineDoc();
    Y.applyUpdate(left, Y.encodeStateAsUpdate(base));
    Y.applyUpdate(right, Y.encodeStateAsUpdate(base));
    const leftNode = left.getMap<Y.Map<unknown>>("sdpstudio").get("node:a")!;
    const rightNode = right.getMap<Y.Map<unknown>>("sdpstudio").get("node:a")!;
    leftNode.set("position", JSON.stringify({ x: 10, y: 20 }));
    rightNode.set("config", JSON.stringify({ table: "customers" }));
    Y.applyUpdate(left, Y.encodeStateAsUpdate(right));
    const merged = readPipelineDoc(left)!;
    expect(merged.nodes[0].position).toEqual({ x: 10, y: 20 });
    expect(merged.nodes[0].config.table).toBe("customers");
  });

  it("synchronizes language-scoped source text", () => {
    const first = createPipelineDoc();
    setSourceText(first, "python", "print(1)");
    const second = createPipelineDoc();
    Y.applyUpdate(second, Y.encodeStateAsUpdate(first));
    expect(sourceText(second, "python").toString()).toBe("print(1)");
    expect(sourceText(second, "sql").toString()).toBe("");
  });

  it("binds arbitrary normalized project files to shared Y.Text values", () => {
    const doc = createPipelineDoc();
    setProjectFileText(doc, "src/helper.py", "print(1)");
    expect(projectFileText(doc, "src/helper.py").toString()).toBe("print(1)");
    expect(() => projectFileText(doc, "../secret.txt")).toThrow(/normalized/);
  });
});

it("builds the normative collaboration websocket URL", () => {
  expect(collaborationWebSocketUrl("project a", { protocol: "http:", host: "localhost:8787" })).toBe("ws://localhost:8787/ws/collab/project%20a");
  expect(collaborationWebSocketUrl("secure", { protocol: "https:", host: "studio.example" })).toBe("wss://studio.example/ws/collab/secure");
});

it("persists and restores offline Yjs state per project", () => {
  const first = createPipelineDoc();
  setPipelineDoc(first, { nodes: [{ id: "n1", type: "source.table", position: { x: 0, y: 0 }, config: { name: "offline" } }], edges: [] });
  persistOfflineState("p1", first);
  const second = createPipelineDoc();
  expect(restoreOfflineState("p1", second)).toBe(true);
  expect(readPipelineDoc(second)?.nodes[0]?.config.name).toBe("offline");
});
