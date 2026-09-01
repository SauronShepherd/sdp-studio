import { useState } from "react";

export type QuickStartStep = { id: string; title: string; description: string; action: string };

export const QUICK_START_STEPS: QuickStartStep[] = [
  { id: "sample", title: "Create the sample project", description: "Open the retail pipeline example.", action: "Create sample" },
  { id: "runtime", title: "Select local Spark 4.2", description: "Use the local runtime profile with no provider credentials.", action: "Select local" },
  { id: "design", title: "Design the pipeline", description: "Inspect the visual source, transform, and output graph.", action: "Open canvas" },
  { id: "generate", title: "Generate portable code", description: "Generate deterministic Python source from the canonical model.", action: "Generate code" },
  { id: "validate", title: "Validate the model", description: "Run graph, capability, and code-generation validation.", action: "Validate" },
  { id: "dry-run", title: "Preview and dry-run", description: "Inspect bounded preview rows and the captured plan.", action: "Preview" },
  { id: "run", title: "Run the pipeline", description: "Submit the local Spark pipeline and inspect its status.", action: "Run" },
  { id: "debug", title: "Inspect debugger output", description: "Open plans, node snapshots, metrics, and Row Trace.", action: "Open debugger" },
];

type Props = {
  onAction: (step: QuickStartStep) => void | Promise<void>;
  onDismiss: () => void;
};

export function QuickStartWizard({ onAction, onDismiss }: Props) {
  const [current, setCurrent] = useState(0);
  const [busy, setBusy] = useState(false);
  const step = QUICK_START_STEPS[current];
  const complete = () => {
    if (current === QUICK_START_STEPS.length - 1) onDismiss();
    else setCurrent((value) => value + 1);
  };
  return <section className="quick-start-wizard" aria-label="Quick start wizard">
    <header><div><p className="eyebrow">Guided first run</p><h2>Build your first SDP pipeline</h2></div><button className="preview" onClick={onDismiss}>Close</button></header>
    <p className="muted">Step {current + 1} of {QUICK_START_STEPS.length}: {step.description}</p>
    <ol aria-label="Quick start steps">{QUICK_START_STEPS.map((item, index) => <li key={item.id} aria-current={index === current ? "step" : undefined} className={index < current ? "complete" : index === current ? "active" : ""}>{item.title}</li>)}</ol>
    <div className="quick-start-actions"><strong>{step.title}</strong><button className="generate" disabled={busy} onClick={() => { const result = onAction(step); if (result && typeof result.then === "function") { setBusy(true); void result.then(complete).finally(() => setBusy(false)); } else complete(); }}>{busy ? "Working…" : step.action}</button></div>
  </section>;
}
