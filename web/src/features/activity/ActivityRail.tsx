import { useEffect, useState } from "react";

type Props = {
  theme: "dark" | "light";
  activeSection: string;
  onSelect: (section: string) => void;
  onToggleTheme: () => void;
  commands?: Array<{ id: string; label: string; run: () => void }>;
};

export function ActivityRail({ theme, activeSection, onSelect, onToggleTheme, commands = [] }: Props) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const sections = [
    ["canvas", "Pipeline editor", "⌘", ".canvas"],
    ["explorer", "Explorer", "▤", ".explorer-panel"],
    ["operators", "Operators", "◇", ".palette"],
    ["catalog", "Catalog", "▦", ".catalog-panel"],
    ["git", "Git changes", "⑂", ".git-panel"],
    ["runs", "Runs and history", "▶", ".runs"],
    ["debug", "Debug tools", "⌁", ".debug-panel"],
    ["extensions", "Extensions", "⊞", ".extensions-panel"],
    ["settings", "Settings", "⚙", ".status-bar"],
  ] as const;
  const select = (section: string, selector: string) => {
    setPaletteOpen(false);
    onSelect(section);
    document.querySelector(selector)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  return <>
  <nav className="activity-rail" aria-label="Workspace sections">
    {sections.map(([id, label, icon, selector]) => <button className={`rail-item${activeSection === id ? " active" : ""}`} aria-current={activeSection === id ? "page" : undefined} aria-label={label} title={label} key={id} onClick={() => select(id, selector)}>{icon}</button>)}
    <button className="rail-item command-palette-trigger" title="Command palette" aria-label="Open command palette" onClick={() => setPaletteOpen(true)}>⌕</button>
    <button className="rail-item theme-toggle" title="Toggle theme" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={onToggleTheme}>{theme === "dark" ? "☼" : "☾"}</button>
  </nav>
  {paletteOpen && <div className="command-palette" role="dialog" aria-label="Command palette"><h2>Command palette</h2><p className="muted">Choose a workspace section or run a pipeline command</p>{sections.map(([id, label, icon, selector]) => <button key={id} className="palette-command" onClick={() => select(id, selector)}>{icon} {label}</button>)}{commands.map((command) => <button key={command.id} className="palette-command" onClick={() => { setPaletteOpen(false); command.run(); }}>▶ {command.label}</button>)}<button className="palette-close" onClick={() => setPaletteOpen(false)}>Close</button></div>}
  </>;
}
