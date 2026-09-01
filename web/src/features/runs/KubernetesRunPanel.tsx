import { useState } from "react";
import { api } from "../../api";

export function KubernetesRunPanel({ runId }: { runId: string | null }) {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = async (kind: "status" | "probe" | "logs" | "events") => {
    if (!runId) return;
    try { const value = kind === "status" ? await api.kubernetesStatus(runId) : kind === "probe" ? await api.kubernetesProbe(runId) : kind === "logs" ? await api.kubernetesLogs(runId) : await api.kubernetesEvents(runId); setResult(value); setMessage(null); }
    catch (error: unknown) { setMessage(error instanceof Error ? error.message : `Unable to load Kubernetes ${kind}`); }
  };
  return <section aria-label="Kubernetes run details"><h3>Kubernetes run details</h3><button className="preview" disabled={!runId} onClick={() => void load("status")}>Load status</button><button className="preview" disabled={!runId} onClick={() => void load("probe")}>Probe</button><button className="preview" disabled={!runId} onClick={() => void load("logs")}>Load logs</button><button className="preview" disabled={!runId} onClick={() => void load("events")}>Load events</button>{message && <p role="alert">{message}</p>}{result && <pre className="generated" aria-label="Kubernetes run result">{JSON.stringify(result, null, 2)}</pre>}</section>;
}
