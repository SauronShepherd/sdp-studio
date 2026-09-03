import * as Y from "yjs";
import type { Pipeline } from "./api";

const key = "pipeline";
const offlinePrefix = "sdpstudio.collab.";

export function collaborationWebSocketUrl(projectId: string, location: Pick<Location, "protocol" | "host"> = window.location): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/ws/collab/${encodeURIComponent(projectId)}`;
}

export function createPipelineDoc(initial?: Pipeline): Y.Doc {
  const doc = new Y.Doc();
  if (initial) setPipelineDoc(doc, initial);
  return doc;
}

export function setPipelineDoc(doc: Y.Doc, pipeline: Pipeline): void {
  doc.transact(() => {
    const root = doc.getMap<unknown>("sdpstudio");
    root.set("schema", "pipeline-v2");
    root.forEach((_value, id) => {
      if (id.startsWith("node:" ) || id.startsWith("edge:")) root.delete(id);
    });
    pipeline.nodes.forEach((node) => {
      const entry = new Y.Map<unknown>();
      entry.set("id", node.id);
      entry.set("type", node.type);
      entry.set("position", JSON.stringify(node.position));
      entry.set("config", JSON.stringify(node.config));
      root.set(`node:${node.id}`, entry);
    });
    pipeline.edges.forEach((edge) => root.set(`edge:${edge.id}`, JSON.stringify(edge)));
    root.delete(key);
  });
}

export function readPipelineDoc(doc: Y.Doc): Pipeline | null {
  const root = doc.getMap<unknown>("sdpstudio");
  const legacy = root.get(key);
  if (typeof legacy === "string") {
    try { return JSON.parse(legacy) as Pipeline; } catch { return null; }
  }
  try {
    return {
      nodes: Array.from(root.entries()).filter(([id]) => id.startsWith("node:")).map(([, value]) => {
        if (typeof value === "string") return JSON.parse(value) as Pipeline["nodes"][number];
        const entry = value as Y.Map<unknown>;
        return { id: String(entry.get("id") || ""), type: String(entry.get("type") || ""), position: JSON.parse(String(entry.get("position") || '{"x":0,"y":0}')), config: JSON.parse(String(entry.get("config") || "{}")) } as Pipeline["nodes"][number];
      }),
      edges: Array.from(root.entries()).filter(([id]) => id.startsWith("edge:")).map(([, value]) => typeof value === "string" ? JSON.parse(value) : JSON.parse(String(value))),
    } as Pipeline;
  } catch { return null; }
}

export function sourceText(doc: Y.Doc, language: "python" | "sql"): Y.Text {
  return doc.getText(`source:${language}`);
}

export function setSourceText(doc: Y.Doc, language: "python" | "sql", value: string): void {
  const text = sourceText(doc, language);
  doc.transact(() => {
    text.delete(0, text.length);
    text.insert(0, value);
  });
}

/** Collaborative text binding for arbitrary project files, not only generated source. */
export function projectFileText(doc: Y.Doc, path: string): Y.Text {
  if (!path || path.includes("\\") || path.split("/").some((part) => part === ".." || !part)) {
    throw new Error("Project file path must be a normalized relative path");
  }
  return doc.getText(`file:${path}`);
}

export function setProjectFileText(doc: Y.Doc, path: string, value: string): void {
  const text = projectFileText(doc, path);
  doc.transact(() => {
    text.delete(0, text.length);
    text.insert(0, value);
  });
}

export function encodeUpdate(update: Uint8Array): string {
  let binary = "";
  update.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function decodeUpdate(value: string): Uint8Array {
  const padding = (4 - (value.length % 4)) % 4;
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat(padding));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export function persistOfflineState(projectId: string, doc: Y.Doc): void {
  try {
    window.localStorage.setItem(`${offlinePrefix}${projectId}`, encodeUpdate(Y.encodeStateAsUpdate(doc)));
  } catch {
    // Offline recovery is best effort when storage is unavailable or full.
  }
}

export function restoreOfflineState(projectId: string, doc: Y.Doc): boolean {
  try {
    const encoded = window.localStorage.getItem(`${offlinePrefix}${projectId}`);
    if (!encoded) return false;
    Y.applyUpdate(doc, decodeUpdate(encoded), "offline");
    return true;
  } catch {
    return false;
  }
}
