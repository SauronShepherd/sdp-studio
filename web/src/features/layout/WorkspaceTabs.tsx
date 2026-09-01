const tabs = [
  ["canvas", "Canvas", ".canvas"],
  ["code", "Code", ".code-panel, .file-editor"],
  ["diff", "Diff", ".git-graph-diff, .git-conflict-preview"],
  ["comparison", "Run Comparison", ".run-comparison, .run-comparison-panel"],
] as const;

export type WorkspaceView = (typeof tabs)[number][0];

export function WorkspaceTabs({ active = "canvas", onChange }: { active?: WorkspaceView; onChange?: (view: WorkspaceView) => void }) {
  const focus = (id: string, selector: string) => {
    onChange?.(id as WorkspaceView);
    document.querySelector(selector)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  return <nav className="workspace-tabs" aria-label="Workspace views" role="tablist">
    {tabs.map(([id, label, selector]) => <button key={id} id={`workspace-tab-${id}`} className={`workspace-tab${active === id ? " active" : ""}`} role="tab" aria-selected={active === id} aria-controls={`workspace-view-${id}`} onClick={() => focus(id, selector)}>{label}</button>)}
    <span id="workspace-view-code" hidden aria-hidden="true" />
  </nav>;
}
