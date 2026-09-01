import { useEffect } from "react";

export type WorkspaceLayout = { paletteWidth: number; inspectorWidth: number; paletteCollapsed: boolean; inspectorCollapsed: boolean };
const KEY = "sdpstudio.workspace-layout";
const defaults: WorkspaceLayout = { paletteWidth: 220, inspectorWidth: 260, paletteCollapsed: false, inspectorCollapsed: false };
export function readWorkspaceLayout(): WorkspaceLayout {
  try { return { ...defaults, ...JSON.parse(window.localStorage.getItem(KEY) || "{}") }; } catch { return defaults; }
}
export function WorkspaceLayoutControls({ value, onChange }: { value: WorkspaceLayout; onChange: (value: WorkspaceLayout) => void }) {
  useEffect(() => {
    document.documentElement.style.setProperty("--palette-width", value.paletteCollapsed ? "0px" : `${value.paletteWidth}px`);
    document.documentElement.style.setProperty("--inspector-width", value.inspectorCollapsed ? "0px" : `${value.inspectorWidth}px`);
    document.documentElement.toggleAttribute("data-palette-collapsed", value.paletteCollapsed);
    document.documentElement.toggleAttribute("data-inspector-collapsed", value.inspectorCollapsed);
  }, [value]);
  const update = (next: WorkspaceLayout) => { onChange(next); window.localStorage.setItem(KEY, JSON.stringify(next)); };
  return <section className="workspace-layout-controls" aria-label="Workspace layout"><span>Panels</span>
    <button className="preview" aria-pressed={!value.paletteCollapsed} onClick={() => update({ ...value, paletteCollapsed: !value.paletteCollapsed })}>{value.paletteCollapsed ? "Show palette" : "Hide palette"}</button>
    <label>Palette <input aria-label="Palette width" type="range" min="180" max="420" value={value.paletteWidth} disabled={value.paletteCollapsed} onChange={(e) => update({ ...value, paletteWidth: Number(e.target.value) })} /></label>
    <button className="preview" aria-pressed={!value.inspectorCollapsed} onClick={() => update({ ...value, inspectorCollapsed: !value.inspectorCollapsed })}>{value.inspectorCollapsed ? "Show inspector" : "Hide inspector"}</button>
    <label>Inspector <input aria-label="Inspector width" type="range" min="220" max="480" value={value.inspectorWidth} disabled={value.inspectorCollapsed} onChange={(e) => update({ ...value, inspectorWidth: Number(e.target.value) })} /></label>
  </section>;
}
