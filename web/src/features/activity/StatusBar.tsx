type Props = { projectId: string | null; nodes: number; edges: number; runtimeName?: string; collaborators: number; executionHealth?: string | null; branch?: string | null; dirty?: boolean };

export function StatusBar({ projectId, nodes, edges, runtimeName, collaborators, executionHealth, branch, dirty }: Props) {
  return <footer className="status-bar" aria-label="Editor status"><span>{projectId ? `Project ${projectId}` : "No project selected"}</span><span>{nodes} nodes · {edges} connections</span><span>{runtimeName ? `Runtime: ${runtimeName}` : "Default runtime"}</span>{branch && <span aria-label="Git status">{branch} · {dirty ? "dirty" : "clean"}</span>}<span>{collaborators} collaborator{collaborators === 1 ? "" : "s"}</span>{executionHealth && <span aria-label="Execution health">{executionHealth}</span>}</footer>;
}
