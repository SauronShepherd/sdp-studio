import { useState } from "react";

type Props = { stages: Array<Record<string, unknown>> };

export function ExecutionHealthPanel({ stages }: Props) {
  const [expanded, setExpanded] = useState(true);
  if (stages.length === 0) return null;
  return <section className="execution-health" aria-label="Execution health details"><div className="run-row"><h3>Execution health</h3><button className="preview" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>{expanded ? "Hide metrics" : "Show metrics"}</button></div>{expanded && stages.slice(0, 20).map((stage, index) => { const skew = Number(stage.skew_score || 0); const risk = skew >= 5 ? "high" : skew >= 2 ? "medium" : "low"; return <div className={`health-stage risk-${risk}`} key={String(stage.stage_id ?? index)}><div className="run-row"><span>Stage {String(stage.stage_id ?? index)}</span><small>{risk} skew · {String(stage.task_count ?? 0)} tasks</small></div><small>max {String(stage.max_task_ms ?? 0)} ms · shuffle read {String(stage.shuffle_read_bytes ?? 0)} · write {String(stage.shuffle_write_bytes ?? 0)}</small></div>; })}</section>;
}
