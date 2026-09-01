"""Run the real preview compiler against a local Spark session under WSL."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from sdpstudio_codegen import generate_preview_script
from sdpstudio_core.models import Edge, Node, PipelineDocument

root = Path(__file__).resolve().parents[1]
data = root / "tests" / "spark_preview_orders.csv"
data.write_text(
    "id,status,amount\n1,COMPLETE,10.5\n2,CANCELLED,4.0\n3,COMPLETE,2.5\n", encoding="utf-8"
)
source = Node(
    type="source.file",
    config={
        "path": str(data),
        "format": "csv",
        "options": {"header": "true", "inferSchema": "true"},
    },
)
filt = Node(type="transform.filter", config={"expression": "status = 'COMPLETE'"})
edges = [Edge.model_validate({"from": {"node": source.id}, "to": {"node": filt.id, "port": "in"}})]
document = PipelineDocument(name="spark-preview", nodes=[source, filt], edges=edges)
script, problems = generate_preview_script(document, filt.id, limit=10)
if script is None or any(problem.severity == "error" for problem in problems):
    raise SystemExit(str([problem.model_dump() for problem in problems]))
namespace = {"__name__": "__main__"}
exec(compile(script, "<generated-preview>", "exec"), namespace)
