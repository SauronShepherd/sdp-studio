from pathlib import Path

path = Path("web/src/main.tsx")
text = path.read_text(encoding="utf-8")
old = '''    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socketUrl = `${protocol}//${window.location.host}/ws/projects/${projectId}`;'''
new = '''    const protocol = import.meta.env.DEV ? "ws:" : window.location.protocol === "https:" ? "wss:" : "ws:";
    const socketHost = import.meta.env.DEV ? `${window.location.hostname}:8788` : window.location.host;
    const socketUrl = `${protocol}//${socketHost}/ws/projects/${projectId}`;'''
if old not in text:
    raise SystemExit("websocket URL block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
