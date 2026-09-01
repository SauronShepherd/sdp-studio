import { calculateGridLayout, type LayoutEdge, type LayoutItem } from "./layout";

self.onmessage = <T extends LayoutItem>(event: MessageEvent<{ nodes: T[]; edges: LayoutEdge[] }>) => {
  self.postMessage(calculateGridLayout(event.data.nodes, event.data.edges));
};
