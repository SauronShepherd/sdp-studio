import type { OperatorField } from "../../api";

type Props = { fields: OperatorField[]; value: string; onChange: (value: string) => void };

export function SchemaInspector({ fields, value, onChange }: Props) {
  let config: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(value || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) config = parsed as Record<string, unknown>;
  } catch { /* Preserve raw JSON below while it is being edited. */ }
  const update = (name: string, next: unknown) => onChange(JSON.stringify({ ...config, [name]: next }, null, 2));
  return <div className="schema-inspector" aria-label="Schema-driven configuration">{fields.map((field) => {
    const current = config[field.name];
    if (field.type === "boolean") return <label className="field-hint" key={field.name}><input type="checkbox" checked={Boolean(current)} onChange={(event) => update(field.name, event.target.checked)} /> {field.label}</label>;
    const options = (field as OperatorField & { options?: unknown[] }).options;
    if (field.type === "enum" && Array.isArray(options)) return <label className="field-hint" key={field.name}>{field.label}<select value={String(current ?? "")} onChange={(event) => update(field.name, event.target.value)}><option value="">Select…</option>{options.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select></label>;
    if (field.type === "number") return <label className="field-hint" key={field.name}>{field.label}{field.required ? " *" : ""}<input type="number" aria-label={field.label} value={typeof current === "number" ? String(current) : ""} onChange={(event) => update(field.name, event.target.value === "" ? undefined : Number(event.target.value))} /></label>;
    if (field.type === "expression" || field.type === "json") return <label className="field-hint" key={field.name}>{field.label}{field.required ? " *" : ""}<textarea aria-label={field.label} value={typeof current === "string" ? current : JSON.stringify(current ?? "")} onChange={(event) => update(field.name, event.target.value)} rows={3} /></label>;
    return <label className="field-hint" key={field.name}>{field.label}{field.required ? " *" : ""}<input aria-label={field.label} value={typeof current === "string" || typeof current === "number" ? String(current) : ""} onChange={(event) => update(field.name, event.target.value)} /></label>;
  })}</div>;
}
