import { useEffect, useState } from "react";
import MonacoEditor from "@monaco-editor/react";
import { api, type ProjectFile } from "../../api";
import type * as Y from "yjs";
import { projectFileText, setProjectFileText } from "../../collab";

type FileContent = { path: string; content: string; etag: string };
type Props = {
  projectId: string | null;
  files: ProjectFile[];
  readFile?: (projectId: string, path: string) => Promise<FileContent>;
  writeFile?: (projectId: string, path: string, content: string, etag?: string) => Promise<ProjectFile>;
  onChanged?: () => void;
  collaborativeDoc?: Y.Doc | null;
};

export function FileEditor({ projectId, files, readFile = api.readFile, writeFile = api.writeFile, onChanged, collaborativeDoc }: Props) {
  const [path, setPath] = useState("");
  const [openPaths, setOpenPaths] = useState<string[]>([]);
  const [content, setContent] = useState("");
  const [etag, setEtag] = useState("");
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!path || !projectId) return;
    void readFile(projectId, path).then((file) => {
      const shared = collaborativeDoc ? projectFileText(collaborativeDoc, path).toString() : "";
      setContent(shared || file.content);
      setEtag(file.etag);
      setDirty(false);
    }).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "Unable to load file"));
  }, [path, projectId, readFile, collaborativeDoc]);

  useEffect(() => {
    if (!collaborativeDoc || !path) return;
    const shared = projectFileText(collaborativeDoc, path);
    const observe = () => setContent(shared.toString());
    shared.observe(observe);
    return () => shared.unobserve(observe);
  }, [collaborativeDoc, path]);

  const open = (nextPath: string) => {
    setPath(nextPath);
    if (nextPath) setOpenPaths((current) => current.includes(nextPath) ? current : [...current, nextPath]);
  };
  const close = (closedPath: string) => {
    const remaining = openPaths.filter((item) => item !== closedPath);
    setOpenPaths(remaining);
    if (path === closedPath) setPath(remaining[remaining.length - 1] || "");
  };

  const save = async () => {
    if (!projectId || !path) return;
    try {
      const updated = await writeFile(projectId, path, content, etag);
      setEtag(updated.etag || etag);
      setDirty(false);
      setMessage("Saved");
      onChanged?.();
    } catch (error: unknown) {
      const isConflict = error instanceof Error && error.message.includes("409");
      setConflict(isConflict);
      setMessage(isConflict ? "File changed on the server; reload before saving" : error instanceof Error ? error.message : "Unable to save file");
    }
  };

  const createDirectory = async () => {
    if (!projectId) return;
    const directory = window.prompt("Directory path");
    if (!directory?.trim()) return;
    try { await api.createDirectory(projectId, directory.trim()); setMessage("Directory created"); onChanged?.(); }
    catch (error: unknown) { setMessage(error instanceof Error ? error.message : "Unable to create directory"); }
  };

  const createFile = async () => {
    if (!projectId) return;
    const nextPath = window.prompt("New file path");
    if (!nextPath?.trim()) return;
    try {
      const created = await writeFile(projectId, nextPath.trim(), "");
      setPath(created.path);
      setOpenPaths((current) => current.includes(created.path) ? current : [...current, created.path]);
      setContent("");
      setEtag(created.etag || "");
      setDirty(false);
      setMessage("File created");
      onChanged?.();
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : "Unable to create file");
    }
  };

  const rename = async () => {
    if (!projectId || !path) return;
    const nextPath = window.prompt("New file path", path);
    if (!nextPath?.trim() || nextPath.trim() === path) return;
    try { const updated = await api.renameFile(projectId, path, nextPath.trim(), etag); setOpenPaths((current) => current.map((item) => item === path ? updated.path : item)); setPath(updated.path); setEtag(updated.etag || ""); setMessage("File renamed"); onChanged?.(); }
    catch (error: unknown) { setMessage(error instanceof Error && error.message.includes("409") ? "File changed on the server; reload before renaming" : error instanceof Error ? error.message : "Unable to rename file"); }
  };

  const remove = async () => {
    if (!projectId || !path || !window.confirm(`Delete ${path}?`)) return;
    try { await api.deleteFile(projectId, path, etag); setOpenPaths((current) => current.filter((item) => item !== path)); setPath(""); setContent(""); setEtag(""); setDirty(false); setMessage("File deleted"); onChanged?.(); }
    catch (error: unknown) { setMessage(error instanceof Error && error.message.includes("409") ? "File changed on the server; reload before deleting" : error instanceof Error ? error.message : "Unable to delete file"); }
  };

  return <section className="file-editor" aria-label="File editor">
    <label>File <select aria-label="File to edit" value={path} onChange={(event) => open(event.target.value)}>
      <option value="">Select a project file</option>{files.filter((file) => file.kind === "file").map((file) => <option key={file.path} value={file.path}>{file.path}</option>)}
    </select></label>
    {openPaths.length > 0 && <div className="file-editor-tabs" role="tablist" aria-label="Open files">{openPaths.map((openPath) => <div className="file-editor-tab" role="tab" aria-selected={path === openPath} key={openPath}><button className="preview" onClick={() => open(openPath)}>{openPath}{path === openPath && dirty ? " *" : ""}</button><button className="preview" aria-label={`Close ${openPath}`} onClick={() => close(openPath)}>×</button>{path === openPath && conflict && <small role="alert">Conflict</small>}</div>)}</div>}
    <div className="file-editor-monaco" aria-label="Project code editor"><MonacoEditor height="260px" language={path.endsWith(".sql") ? "sql" : path.endsWith(".yaml") || path.endsWith(".yml") ? "yaml" : "python"} theme="vs-dark" value={content} onChange={(value) => { const next = value || ""; setContent(next); if (collaborativeDoc && path) setProjectFileText(collaborativeDoc, path, next); setDirty(true); }} options={{ minimap: { enabled: false }, wordWrap: "on", readOnly: !path, fontSize: 12 }} /></div>
    <textarea className="file-editor-accessibility-buffer" aria-label="File contents" value={content} onChange={(event) => { const next = event.target.value; setContent(next); if (collaborativeDoc && path) setProjectFileText(collaborativeDoc, path, next); setDirty(true); }} disabled={!path} tabIndex={-1} />
    <button className="preview" onClick={() => void save()} disabled={!path || !etag}>Save file</button>
    {conflict && <button className="preview" onClick={() => { if (projectId && path) void readFile(projectId, path).then((file) => { setContent(file.content); setEtag(file.etag); setDirty(false); setConflict(false); setMessage("Reloaded"); }); }}>Reload file</button>}
    <button className="preview" onClick={() => void createFile()} disabled={!projectId}>Create file</button>
    <button className="preview" onClick={() => void createDirectory()} disabled={!projectId}>Create directory</button>
    <button className="preview" onClick={() => void rename()} disabled={!path || !etag}>Rename file</button>
    <button className="preview" onClick={() => void remove()} disabled={!path || !etag}>Delete file</button>
    {message && <p role="status">{message}</p>}
  </section>;
}
