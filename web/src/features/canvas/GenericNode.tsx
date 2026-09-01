import { Handle, Position, type NodeProps } from "@xyflow/react";

type GenericData = {
  nodeId?: string;
  onSelect?: () => void;
  label?: string; operatorId?: string; inputs?: string[]; outputs?: string[];
  health?: string; healthDetail?: string; mode?: "batch" | "streaming";
  materialization?: string; provider?: string; status?: "warning" | "failed" | "running" | "cached-preview";
  metrics?: Record<string, string | number>;
  overlayMetric?: string; overlayValue?: string | number;
};

export function GenericNode({ data, selected }: NodeProps & { data: GenericData }) {
  return <div className={`generic-node${selected ? " selected" : ""}`} data-sdp-node-id={data.nodeId} onClick={() => data.onSelect?.()} role="group" aria-label={`${data.label || data.operatorId || "Operator"} node`}>
    {(data.inputs?.length ? data.inputs : ["in"]).map((port, index, ports) => <Handle key={`input-${port}`} type="target" position={Position.Left} id={port} style={{ top: `${((index + 1) / (ports.length + 1)) * 100}%` }} aria-label={port === "in" ? "Input" : `Input ${port}`} />)}
    <button type="button" className="node-select" aria-label={`Select ${data.label || data.operatorId || "Operator"}`} onPointerDown={(event) => { event.stopPropagation(); data.onSelect?.(); }} onMouseDown={(event) => { event.stopPropagation(); data.onSelect?.(); }} onClick={(event) => { event.stopPropagation(); data.onSelect?.(); }}><strong>{data.label || data.operatorId || "Operator"}</strong></button>
    <small>{data.operatorId || "custom"}</small>
    <div className="node-badges" aria-label="Node status badges">
      {data.mode && <span className={`node-badge mode-${data.mode}`}>{data.mode}</span>}
      {data.materialization && <span className="node-badge materialization">{data.materialization}</span>}
      {data.provider && <span className="node-badge provider">{data.provider}</span>}
      {data.status && <span className={`node-badge status-${data.status}`}>{data.status}</span>}
      {data.metrics && Object.entries(data.metrics).map(([key, value]) => <span className="node-badge metric" key={key} aria-label={`${key}: ${value}`}>{key}: {value}</span>)}
      {data.overlayMetric && <span className="node-badge metric overlay" aria-label={`${data.overlayMetric}: ${data.overlayValue}`}>{data.overlayMetric}: {data.overlayValue}</span>}
    </div>
    {data.health && <span className={`node-health ${data.health}`} title={data.healthDetail}>{data.health}</span>}
    {(data.outputs?.length ? data.outputs : ["out"]).map((port, index, ports) => <Handle key={`output-${port}`} type="source" position={Position.Right} id={port} style={{ top: `${((index + 1) / (ports.length + 1)) * 100}%` }} aria-label={port === "out" ? "Output" : `Output ${port}`} />)}
  </div>;
}
