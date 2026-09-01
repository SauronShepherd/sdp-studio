import type { PreviewResult, ProfileResult } from "../../api";

export function PreviewTable({ result }: { result: PreviewResult }) {
  const columns = result.schema.length > 0 ? result.schema.map((field) => typeof field === "string" ? field : String((field as { name?: unknown }).name || "")) : Object.keys(result.rows[0] || {});
  return <section aria-label="Preview data"><div className="preview-summary"><strong>{result.rows.length} of {result.limit} rows</strong><span>{columns.length} columns</span>{result.cache && <span role="status">{result.cache.hit ? `Cached · ${result.cache.age_seconds}s old` : "Fresh preview"}</span>}</div>{result.rows.length === 0 ? <p className="muted">No rows returned.</p> : <div className="preview-table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.slice(0, result.limit).map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}</tr>)}</tbody></table></div>}{result.profile && <ProfileSummary profile={result.profile} />}</section>;
}

function ProfileSummary({ profile }: { profile: ProfileResult }) {
  return <section aria-label="Preview profile"><h3>Profile</h3><span>{profile.row_count} rows analyzed</span><ul>{Object.entries(profile.columns).slice(0, 12).map(([name, column]) => <li key={name}><strong>{name}</strong>: {column.null_count} null, {column.distinct_count} distinct</li>)}</ul></section>;
}

function formatValue(value: unknown): string { if (value === null || value === undefined) return "—"; if (typeof value === "object") return JSON.stringify(value); return String(value); }
