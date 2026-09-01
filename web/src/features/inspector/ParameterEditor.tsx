type ParameterNode = { id: string; config: Record<string, unknown> };
const KINDS = ["string", "int", "float", "bool", "date", "timestamp", "secret-ref", "enum", "JSON"] as const;
type ParameterKind = typeof KINDS[number];

type Props = { parameters: ParameterNode[]; onChange: (nodeId: string, config: Record<string, unknown>) => void };

export function ParameterEditor({ parameters, onChange }: Props) {
  if (parameters.length === 0) return null;
  return <section aria-label="Project parameters"><h2>Project parameters</h2>{parameters.map((parameter) => {
    const name = String(parameter.config.name || parameter.id);
    const kind = (KINDS.includes(parameter.config.kind as ParameterKind) ? parameter.config.kind : "string") as ParameterKind;
    const update = (value: string) => {
      let parsed: unknown = value;
      if (kind === "int") parsed = value === "" ? "" : Number.parseInt(value, 10);
      if (kind === "float") parsed = value === "" ? "" : Number.parseFloat(value);
      if (kind === "bool") parsed = value === "true";
      if (kind === "JSON") { try { parsed = JSON.parse(value); } catch { parsed = value; } }
      const next: Record<string, unknown> = { ...parameter.config, default: parsed };
      if (parameter.config.kind || kind !== "string") next.kind = kind;
      onChange(parameter.id, next);
    };
    return <div className="parameter-field" key={parameter.id}><label className="field-hint">{name}<select aria-label={`Parameter type ${name}`} value={kind} onChange={(event) => onChange(parameter.id, { ...parameter.config, kind: event.target.value })}>{KINDS.map((item) => <option value={item} key={item}>{item}</option>)}</select><input aria-label={`Parameter ${name}`} type={kind === "bool" ? "checkbox" : "text"} checked={kind === "bool" ? parameter.config.default === true : undefined} value={kind === "bool" ? undefined : String(parameter.config.default ?? "")} placeholder={kind === "secret-ref" ? "secret://NAME" : undefined} onChange={(event) => update(kind === "bool" ? String(event.target.checked) : event.target.value)} /></label></div>;
  })}</section>;
}
