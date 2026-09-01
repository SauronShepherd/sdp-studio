type TraceStep = { node_id?: string; type?: string; input_count?: number; output_count?: number; trace_status?: string; rows?: unknown[]; trace_summary?: unknown[] };

type TraceResult = { node_id?: string; trace_mode?: string; provenance?: string; trace_instrumentation?: string; steps?: TraceStep[]; rows?: unknown[]; unsupported?: unknown[]; [key: string]: unknown };

export function RowTracePanel({ value }: { value: string }) {
  let result: TraceResult;
  try { result = JSON.parse(value) as TraceResult; } catch { return <pre className="generated" aria-label="Row trace result">{value}</pre>; }
  return <section className="trace-panel" aria-label="Row trace result"><div className="run-row"><strong>Row trace</strong><small>{result.trace_mode || "unknown"} · {result.provenance || "unknown"}</small></div>{result.trace_instrumentation && <p className="muted">Spark instrumentation: {result.trace_instrumentation}</p>}<ol>{(result.steps || []).map((step, index) => <li key={`${step.node_id || "step"}-${index}`}><div className="run-row"><span>{step.node_id || step.type || "step"}</span><small>{step.trace_status || "unknown"} · {step.input_count ?? 0} → {step.output_count ?? 0} rows</small></div></li>)}</ol>{(result.unsupported || []).length > 0 && <p className="muted">Some downstream operators have unknown provenance.</p>}</section>;
}
