import { StrictMode, useCallback, useEffect, useRef, useState, type ComponentProps, type DragEvent } from "react";
import { createRoot } from "react-dom/client";
import MonacoEditor, { type OnMount } from "@monaco-editor/react";
import { addEdge, Background, Controls, MiniMap, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, type Connection, type Edge, type Node } from "@xyflow/react";
import "./shell.css";
import { api, type CapabilityProblem, type GitBranches, type GitCommit, type GitRemotes, type GitStatus, type HistorySnapshot, type Operator, type Pipeline, type PreviewResult, type Project, type ProjectCatalog, type ProjectFile, type ProviderRepository, type ProviderReview, type RuntimeCapabilities, type RuntimeProfile, type Schedule } from "./api";
import * as Y from "yjs";
import { createPipelineDoc, decodeUpdate, encodeUpdate, persistOfflineState, readPipelineDoc, restoreOfflineState, setPipelineDoc, setSourceText, sourceText } from "./collab";
import { ActivityRail } from "./features/activity/ActivityRail";
import { StatusBar } from "./features/activity/StatusBar";
import { RuntimeProfilePanel } from "./features/runtime/RuntimeProfilePanel";
import { ProblemsPanel } from "./features/debug/ProblemsPanel";
import { ExecutionHealthPanel } from "./features/debug/ExecutionHealthPanel";
import { cloneNodeForPaste } from "./features/canvas/clipboard";
import { validateConnection } from "./features/canvas/edgeValidation";
import { SchemaInspector } from "./features/inspector/SchemaInspector";
import { ParameterEditor } from "./features/inspector/ParameterEditor";
import { PlanInspector } from "./features/debug/PlanInspector";
import { PreviewTable } from "./features/debug/PreviewTable";
import { ScheduleForm } from "./features/schedules/ScheduleForm";
import { RunComparisonPanel } from "./features/debug/RunComparisonPanel";
import { RunComparisonSelector } from "./features/debug/RunComparisonSelector";
import { RowTracePanel } from "./features/debug/RowTracePanel";
import { GitGraphDiffPanel } from "./features/git/GitGraphDiffPanel";
import { layoutInWorker } from "./features/canvas/layout";
import { GenericNode } from "./features/canvas/GenericNode";
import { AuthPanel } from "./features/auth/AuthPanel";
import { GraphOutline } from "./features/canvas/GraphOutline";
import { FileEditor } from "./features/explorer/FileEditor";
import { KubernetesRunPanel } from "./features/runs/KubernetesRunPanel";

export const isTerminalRunStatus = (status: string | null | undefined): boolean =>
  ["succeeded", "validation_failed", "failed", "cancelled", "lost"].includes(String(status));
import { readWorkspaceLayout, WorkspaceLayoutControls, type WorkspaceLayout } from "./features/layout/WorkspaceLayoutControls";
import { WorkspaceTabs, type WorkspaceView } from "./features/layout/WorkspaceTabs";
import { QuickStartWizard, type QuickStartStep } from "./features/onboarding/QuickStartWizard";

const nodeTypes = { generic: GenericNode };
type SourceMapEntry = { node_id?: string | null; start_line: number; end_line: number; start_column?: number | null; end_column?: number | null; file?: string };
type PresenceState = { selected_node_id?: string | null; cursor?: { line?: number; column?: number } | null };
type MetricOverlay = "duration" | "rows" | "bytes" | "shuffle" | "skew" | "quality" | "freshness" | "compatibility";

function visualNodeData(node: Pipeline["nodes"][number], operator?: Operator) {
  const streaming = node.type === "source.kafka" || node.config.streaming === true;
  const materialization = node.type.startsWith("dataset.") ? node.type.slice("dataset.".length) : undefined;
  return {
    nodeId: node.id,
    label: node.config.name || node.config.table || node.type,
    operatorId: node.type,
    inputs: operator?.inputs,
    outputs: operator?.outputs,
    mode: streaming ? "streaming" as const : "batch" as const,
    materialization,
    provider: typeof node.config.provider === "string" ? node.config.provider : undefined,
    metrics: node.config.metrics && typeof node.config.metrics === "object"
      ? Object.fromEntries(Object.entries(node.config.metrics as Record<string, unknown>).filter(([, value]) => typeof value === "string" || typeof value === "number")) as Record<string, string | number>
      : undefined,
  };
}

let activeCollabDoc: Y.Doc | null = null;
let activeEditorRole: string | null = null;

function Editor(props: ComponentProps<typeof MonacoEditor>) {
  const language = props.language === "sql" ? "sql" : "python";
  const readOnly = activeEditorRole === "viewer";
  return <MonacoEditor {...props} options={{ ...props.options, readOnly }} onChange={(value) => {
    if (value === undefined || readOnly) return;
    if (activeCollabDoc) setSourceText(activeCollabDoc, language, value);
  }} />;
}

export function App() {
  const [operators, setOperators] = useState<Operator[]>([]);
  const [operatorQuery, setOperatorQuery] = useState("");
  const [pipeline, setPipeline] = useState<Pipeline>({ nodes: [], edges: [] });
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [configText, setConfigText] = useState("{}");
  const [runtime, setRuntime] = useState<RuntimeCapabilities | null>(null);
  const [runtimeProfiles, setRuntimeProfiles] = useState<RuntimeProfile[]>([]);
  const [runtimeProfileId, setRuntimeProfileId] = useState("");
  const [runtimeProfileMessage, setRuntimeProfileMessage] = useState<string | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [problems, setProblems] = useState<CapabilityProblem[]>([]);
  const [generated, setGenerated] = useState<string | null>(null);
  const [generatedLanguage, setGeneratedLanguage] = useState<"python" | "sql">("python");
  const [generatedSourceMap, setGeneratedSourceMap] = useState<SourceMapEntry[]>([]);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runs, setRuns] = useState<Array<{ id: string; status: string }>>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [gitStatus, setGitStatus] = useState<GitStatus | null>(null);
  const [gitRemotes, setGitRemotes] = useState<GitRemotes>({});
  const [gitBranches, setGitBranches] = useState<GitBranches>({ current: null, branches: [] });
  const [gitLog, setGitLog] = useState<GitCommit[]>([]);
  const [gitDiff, setGitDiff] = useState<string | null>(null);
  const [gitTags, setGitTags] = useState<string[]>([]);
  const [gitStashes, setGitStashes] = useState<string[]>([]);
  const [gitConflicts, setGitConflicts] = useState<string[]>([]);
  const [gitConflictPreview, setGitConflictPreview] = useState<{ path: string; ours: string; theirs: string } | null>(null);
  const [gitReviews, setGitReviews] = useState<ProviderReview[]>([]);
  const [gitRepository, setGitRepository] = useState<ProviderRepository | null>(null);
  const [catalog, setCatalog] = useState<ProjectCatalog | null>(null);
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [commitMessage, setCommitMessage] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const [previewRows, setPreviewRows] = useState<Array<Record<string, unknown>>>([]);
  const [previewLimit, setPreviewLimit] = useState(50);
  const [previewIncludeProfile, setPreviewIncludeProfile] = useState(true);
  const [previewIncludePlan, setPreviewIncludePlan] = useState(false);
  const [previewSamplingFraction, setPreviewSamplingFraction] = useState(1);
  const [previewSeed, setPreviewSeed] = useState(0);
  const [previewTimeout, setPreviewTimeout] = useState(120);
  const [previewCacheTtl, setPreviewCacheTtl] = useState(300);
  const [previewForceRefresh, setPreviewForceRefresh] = useState(false);
  const [profile, setProfile] = useState<string | null>(null);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [historySnapshots, setHistorySnapshots] = useState<HistorySnapshot[]>([]);
  const [historyDiff, setHistoryDiff] = useState<string | null>(null);
  const [presence, setPresence] = useState(0);
  const [presenceStates, setPresenceStates] = useState<PresenceState[]>([]);
  const [metricOverlay, setMetricOverlay] = useState<MetricOverlay | null>(null);
  const [showAuthPanel, setShowAuthPanel] = useState(false);
  const [showQuickStart, setShowQuickStart] = useState(() => window.localStorage.getItem("sdpstudio.quick-start.completed") !== "1");
  const generatedEditor = useRef<Parameters<OnMount>[0] | null>(null);
  const pipelineRef = useRef<Pipeline>(pipeline);
  const flowNodesRef = useRef<Node[]>(flowNodes);
  const runsRef = useRef<import("./api").RunRecord[]>(runs);
  const localPipelineDirty = useRef(false);
  const remotePipelineBlockedUntil = useRef(0);
  const canonicalPipelineLoaded = useRef(false);
  const graphSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const graphSaveQueue = useRef<Promise<void>>(Promise.resolve());
  const [authRole, setAuthRole] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState("canvas");
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("canvas");
  const [themeChoice, setThemeChoice] = useState<"dark" | "light" | "system">(() => {
    const saved = window.localStorage.getItem("sdpstudioTheme");
    return saved === "light" || saved === "system" ? saved : "dark";
  });
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [debugPlan, setDebugPlan] = useState<string | null>(null);
  const [rowTrace, setRowTrace] = useState<string | null>(null);
  const [qualityResult, setQualityResult] = useState<string | null>(null);
  const [runComparison, setRunComparison] = useState<string | null>(null);
  const [executionHealth, setExecutionHealth] = useState<string | null>(null);
  const [executionStages, setExecutionStages] = useState<Array<Record<string, unknown>>>([]);
  const [streamingDiagnostics, setStreamingDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [debugBundleManifest, setDebugBundleManifest] = useState<Record<string, unknown> | null>(null);
  const history = useRef<Array<{ nodes: Node[]; edges: Edge[] }>>([]);
  const future = useRef<Array<{ nodes: Node[]; edges: Edge[] }>>([]);
  const [historyDepth, setHistoryDepth] = useState(0);
  const [futureDepth, setFutureDepth] = useState(0);
  const [workspaceLayout, setWorkspaceLayout] = useState<WorkspaceLayout>(() => readWorkspaceLayout());
  const collabSocket = useRef<WebSocket | null>(null);
  const collabDoc = useRef<Y.Doc | null>(null);
  const generatedLanguageRef = useRef<"python" | "sql">("python");
  const generatedRef = useRef<string | null>(null);
  const applyingRemoteUpdate = useRef(false);
  const clipboardNode = useRef<Node | null>(null);
  useEffect(() => { generatedLanguageRef.current = generatedLanguage; }, [generatedLanguage]);
  useEffect(() => { generatedRef.current = generated; }, [generated]);
  useEffect(() => { pipelineRef.current = pipeline; }, [pipeline]);
  useEffect(() => { flowNodesRef.current = flowNodes; }, [flowNodes]);
  useEffect(() => { runsRef.current = runs; }, [runs]);
  useEffect(() => { activeEditorRole = authRole; return () => { activeEditorRole = null; }; }, [authRole]);
  const groupedOperators = operators.filter((operator) => `${operator.title} ${operator.id} ${operator.category}`.toLowerCase().includes(operatorQuery.trim().toLowerCase())).reduce<Record<string, Operator[]>>((groups, operator) => { (groups[operator.category || "Other"] ||= []).push(operator); return groups; }, {});
  const operatorAvailability = (operator: Operator): string | null => {
    if (!runtime) return null;
    const missing = (operator.required_capabilities || []).filter((capability) => runtime[capability as keyof RuntimeCapabilities] !== true);
    if (missing.length) return `Requires: ${missing.join(", ")}`;
    const forbidden = (operator.forbidden_capabilities || []).filter((capability) => runtime[capability as keyof RuntimeCapabilities] === true);
    return forbidden.length ? `Unavailable with: ${forbidden.join(", ")}` : null;
  };

  useEffect(() => {
    const resolve = () => setTheme(themeChoice === "system" && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : themeChoice === "system" ? "dark" : themeChoice);
    resolve();
    const media = window.matchMedia("(prefers-color-scheme: light)");
    media.addEventListener?.("change", resolve);
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("sdpstudioTheme", themeChoice);
    return () => media.removeEventListener?.("change", resolve);
  }, [themeChoice, theme]);

  const recordHistory = (nodes: Node[], edges: Edge[]) => {
    history.current = [...history.current.slice(-49), { nodes, edges }];
    future.current = [];
    setHistoryDepth(history.current.length);
    setFutureDepth(0);
  };

  const saveGraph = async (nodes: Node[], edges: Edge[]) => {
    if (!projectId) return;
    localPipelineDirty.current = true;
    const currentPipeline = pipelineRef.current;
    const configs = new Map(currentPipeline.nodes.map((node) => [node.id, node.config]));
    const next: Pipeline = {
      ...currentPipeline,
      nodes: nodes.map((node) => ({
        id: node.id,
        type: String(node.data.operatorId || node.data.label),
        position: node.position,
        // React Flow owns topology/layout, while the persisted pipeline owns
        // operator configuration. Never replace an existing config during a
        // canvas-only save.
        config: configs.get(node.id) || {},
      })),
      edges: edges.map((edge) => ({ id: edge.id, from: { node: edge.source, port: String(edge.sourceHandle || "out") }, to: { node: edge.target, port: String(edge.targetHandle || edge.label || "in") } })),
    };
    // Keep the imperative snapshot in lockstep with React state. Canvas saves
    // are queued and may be followed by another drag/config edit before the
    // next render, so relying only on the state effect can rebuild from stale
    // topology or configuration.
    pipelineRef.current = next;
    setPipeline(next);
    graphSaveQueue.current = graphSaveQueue.current.then(async () => {
      try {
        await api.savePipeline(projectId, next);
        if (!applyingRemoteUpdate.current && collabDoc.current) setPipelineDoc(collabDoc.current, next);
      } catch (cause: unknown) {
        setError(cause instanceof Error ? cause.message : "Unable to save pipeline");
      }
    });
  };

  const restoreGraph = (nodes: Node[], edges: Edge[]) => {
    setFlowNodes(nodes);
    setFlowEdges(edges);
    scheduleGraphSave(nodes, edges);
  };

  const scheduleGraphSave = (nodes: Node[], edges: Edge[]) => {
    if (graphSaveTimer.current) clearTimeout(graphSaveTimer.current);
    graphSaveTimer.current = setTimeout(() => {
      graphSaveTimer.current = null;
      void saveGraph(nodes, edges);
    }, 450);
  };

  const saveDraggedNode = (_event: unknown, draggedNode: Node) => {
    const nodes = flowNodesRef.current.map((node) => node.id === draggedNode.id ? { ...node, position: draggedNode.position } : node);
    flowNodesRef.current = nodes;
    scheduleGraphSave(nodes, flowEdges);
  };

  const undo = () => {
    const previous = history.current.pop();
    if (!previous) return;
    future.current.push({ nodes: flowNodes, edges: flowEdges });
    setHistoryDepth(history.current.length);
    setFutureDepth(future.current.length);
    restoreGraph(previous.nodes, previous.edges);
  };

  const redo = () => {
    const next = future.current.pop();
    if (!next) return;
    history.current.push({ nodes: flowNodes, edges: flowEdges });
    setHistoryDepth(history.current.length);
    setFutureDepth(future.current.length);
    restoreGraph(next.nodes, next.edges);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key.toLowerCase() === "z") { event.preventDefault(); undo(); }
      if (event.key.toLowerCase() === "y") { event.preventDefault(); redo(); }
      if (event.key.toLowerCase() === "c" && selected) {
        clipboardNode.current = flowNodes.find((node) => node.id === selected) || null;
      }
      if (event.key.toLowerCase() === "v" && clipboardNode.current) {
        event.preventDefault();
        recordHistory(flowNodes, flowEdges);
        const pasted = cloneNodeForPaste(clipboardNode.current, new Set(flowNodes.map((node) => node.id)));
        const nextNodes = [...flowNodes, pasted];
        setFlowNodes(nextNodes);
        setSelected(pasted.id);
        scheduleGraphSave(nextNodes, flowEdges);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  useEffect(() => () => {
    if (graphSaveTimer.current) clearTimeout(graphSaveTimer.current);
  }, []);

  useEffect(() => {
    if (!projectId) {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/projects/${projectId}`, ["sdpstudio.v1"]);
    const doc = createPipelineDoc();
    const recoveredOffline = restoreOfflineState(projectId, doc);
    collabDoc.current = doc;
    activeCollabDoc = doc;
    collabSocket.current = socket;
    const sourceObservers = (["python", "sql"] as const).map((language) => {
      const text = sourceText(doc, language);
      const observer = () => {
        if (generatedLanguageRef.current === language && text.toString() !== generatedRef.current) setGenerated(text.toString());
      };
      text.observe(observer);
      return () => text.unobserve(observer);
    });
    const onUpdate = (update: Uint8Array, origin: unknown) => {
      persistOfflineState(projectId, doc);
      if (origin === "remote" || !socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({ type: "y_update", update: encodeUpdate(update) }));
    };
    doc.on("update", onUpdate);
    socket.onopen = () => {
      if (recoveredOffline) {
        socket.send(JSON.stringify({ type: "y_update", update: encodeUpdate(Y.encodeStateAsUpdate(doc)) }));
      }
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as { type?: string; count?: number; event?: { update?: string }; snapshot?: { document?: Pipeline | { format?: string; updates?: Array<{ update?: string }> } } };
        if (message.type === "presence" && typeof message.count === "number") setPresence(message.count);
        if (message.type === "presence_state" && Array.isArray((message as { states?: unknown[] }).states)) {
          const states = ((message as { states: PresenceState[] }).states).filter((state) => state && typeof state === "object");
          setPresenceStates(states);
          setPresence(states.length);
        }
        if (message.type === "y_update" && message.event?.update) {
          applyingRemoteUpdate.current = true;
          Y.applyUpdate(doc, decodeUpdate(message.event.update), "remote");
          const remote = readPipelineDoc(doc);
          if (remote && !localPipelineDirty.current && Date.now() >= remotePipelineBlockedUntil.current) setPipeline(remote);
          persistOfflineState(projectId, doc);
          applyingRemoteUpdate.current = false;
        }
        if (message.type === "snapshot" && message.snapshot?.document) {
          const document = message.snapshot.document;
          if ("format" in document && document.format === "yjs-update-bundle") {
            for (const item of document.updates || []) {
              if (item.update) Y.applyUpdate(doc, decodeUpdate(item.update), "remote");
            }
            const recovered = readPipelineDoc(doc);
            if (recovered && !canonicalPipelineLoaded.current && !localPipelineDirty.current && Date.now() >= remotePipelineBlockedUntil.current) setPipeline(recovered);
            persistOfflineState(projectId, doc);
          } else if ("nodes" in document && "edges" in document) {
            setPipelineDoc(doc, document);
            if (!canonicalPipelineLoaded.current && !localPipelineDirty.current && Date.now() >= remotePipelineBlockedUntil.current) setPipeline(document);
            persistOfflineState(projectId, doc);
          }
        }
      } catch {
        // Ignore malformed non-control messages; REST remains the source of truth.
      }
    };
    socket.onerror = () => setPresence(0);
    return () => { sourceObservers.forEach((dispose) => dispose()); doc.off("update", onUpdate); doc.destroy(); collabDoc.current = null; activeCollabDoc = null; collabSocket.current = null; socket.close(); };
  }, [projectId]);

  useEffect(() => {
    Promise.all([api.operators(), api.projects(), api.doctor(), api.runtimeProfiles()])
      .then(async ([catalog, projects, doctor, profiles]) => {
        setOperators(catalog);
        setProjects(projects);
        setRuntime(doctor);
        setRuntimeProfiles(profiles);
        setRuntimeProfileId(profiles[0]?.id || "");
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to load SDP Studio"));
  }, [setFlowEdges, setFlowNodes]);

  const selectProject = async (nextId: string) => {
    try {
      setPresence(0);
      setSelected(null);
      // REST is canonical during project selection; do not let an offline or
      // delayed CRDT snapshot replace the document while it is loading.
      localPipelineDirty.current = true;
      canonicalPipelineLoaded.current = false;
      remotePipelineBlockedUntil.current = Date.now() + 15000;
      setProjectId(nextId);
      const [loaded, projectRuns, projectSchedules, repository, snapshots] = await Promise.all([api.pipeline(nextId), api.runs(nextId), api.schedules(nextId), api.gitStatus(nextId), api.history(nextId)]);
      setPipeline(loaded);
      pipelineRef.current = loaded;
      runsRef.current = projectRuns;
      if (collabDoc.current) setPipelineDoc(collabDoc.current, loaded);
      localPipelineDirty.current = false;
      canonicalPipelineLoaded.current = true;
      setRuns(projectRuns);
      setHistorySnapshots(snapshots);
      setSchedules(projectSchedules);
      setGitStatus(repository);
      setGitDiff(null);
      setFlowNodes(loaded.nodes.map((node) => { const operator = operators.find((item) => item.id === node.type); return { id: node.id, position: node.position, data: visualNodeData(node, operator), type: "generic" }; }));
      setFlowEdges(loaded.edges.map((edge) => ({ id: edge.id, source: edge.from.node, target: edge.to.node, label: edge.to.port })));
      setSelected(loaded.nodes[0]?.id || null);
      setConfigText(JSON.stringify(loaded.nodes[0]?.config || {}, null, 2));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Unable to load project");
    }
  };

  const createHistoryCheckpoint = async () => {
    if (!projectId) return;
    const name = window.prompt("Checkpoint name", "checkpoint");
    if (!name?.trim()) return;
    try {
      const snapshot = await api.createHistoryCheckpoint(projectId, name.trim());
      setHistorySnapshots((current) => [snapshot, ...current]);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Unable to create checkpoint");
    }
  };

  const restoreHistory = async (snapshotId: string) => {
    if (!projectId || !window.confirm("Restore this pipeline snapshot?")) return;
    try {
      const restored = await api.restoreHistory(projectId, snapshotId);
      pipelineRef.current = restored;
      setPipeline(restored);
      setFlowNodes(restored.nodes.map((node) => { const operator = operators.find((item) => item.id === node.type); return { id: node.id, position: node.position, data: visualNodeData(node, operator), type: "generic" }; }));
      setFlowEdges(restored.edges.map((edge) => ({ id: edge.id, source: edge.from.node, target: edge.to.node, label: edge.to.port })));
      setProjectMessage("History snapshot restored");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Unable to restore history");
    }
  };

  const showHistoryDiff = async (snapshotId: string) => {
    if (!projectId) return;
    try { setHistoryDiff(JSON.stringify((await api.historyDiff(projectId, snapshotId)).diff, null, 2)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load history diff"); }
  };

  const loadCatalog = async () => {
    if (!projectId) return;
    try { setCatalog(await api.catalog(projectId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load catalog"); }
  };

  const loadProjectFiles = async () => {
    if (!projectId) return;
    try { setProjectFiles(await api.files(projectId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load project files"); }
  };

  const chooseNode = (nodeId: string) => {
    setSelected(nodeId);
    if (collabSocket.current?.readyState === WebSocket.OPEN) {
      collabSocket.current.send(JSON.stringify({ type: "presence", selected_node_id: nodeId }));
    }
    const model = pipelineRef.current.nodes.find((node) => node.id === nodeId);
    setConfigText(JSON.stringify(model?.config || {}, null, 2));
  };

  const addOperator = (operator: Operator, position?: { x: number; y: number }) => {
    const id = `${operator.id}-${crypto.randomUUID()}`;
    const node: Node = { id, position: position || { x: 120 + flowNodes.length * 30, y: 120 + flowNodes.length * 30 }, data: { label: operator.title, operatorId: operator.id, inputs: operator.inputs, outputs: operator.outputs }, type: "generic" };
    recordHistory(flowNodes, flowEdges);
    const nextNodes = [...flowNodes, node];
    setFlowNodes(nextNodes);
    scheduleGraphSave(nextNodes, flowEdges);
    chooseNode(id);
  };

  const dropOperator = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const operator = operators.find((item) => item.id === event.dataTransfer.getData("application/x-sdpstudio-operator"));
    if (!operator) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    addOperator(operator, { x: Math.max(0, event.clientX - bounds.left), y: Math.max(0, event.clientY - bounds.top) });
  };

  const connect = (connection: Connection) => {
    const problem = validateConnection(connection, flowNodes.map((node) => ({ id: node.id, type: String(node.data.operatorId || node.data.label), config: pipeline.nodes.find((item) => item.id === node.id)?.config })), flowEdges, operators);
    if (problem) { setError(problem); return; }
    const next = addEdge(connection, flowEdges);
    recordHistory(flowNodes, flowEdges);
    setFlowEdges(next);
    scheduleGraphSave(flowNodes, next);
  };

  const deleteNodes = (deleted: Node[]) => {
    recordHistory(flowNodes, flowEdges);
    const deletedIds = new Set(deleted.map((node) => node.id));
    const nextNodes = flowNodes.filter((node) => !deletedIds.has(node.id));
    const nextEdges = flowEdges.filter((edge) => !deletedIds.has(edge.source) && !deletedIds.has(edge.target));
    setFlowNodes(nextNodes);
    setFlowEdges(nextEdges);
    if (selected && deletedIds.has(selected)) setSelected(null);
    scheduleGraphSave(nextNodes, nextEdges);
  };

  const autoLayout = async () => {
    if (flowNodes.length === 0) return;
    recordHistory(flowNodes, flowEdges);
    const layout = await layoutInWorker(flowNodes, flowEdges.map((edge) => ({ source: edge.source, target: edge.target })));
    setFlowNodes(layout);
    scheduleGraphSave(layout, flowEdges);
  };

  const selectedModel = selected ? pipeline.nodes.find((node) => node.id === selected) : undefined;
  const selectedOperator = selectedModel ? operators.find((operator) => operator.id === selectedModel.type) : undefined;
  const saveConfig = async () => {
    if (!selected) return;
    try {
      const config = JSON.parse(configText) as Record<string, unknown>;
      const currentPipeline = pipelineRef.current;
      const nextPipeline = { ...currentPipeline, nodes: currentPipeline.nodes.map((node) => node.id === selected ? { ...node, config } : node) };
      pipelineRef.current = nextPipeline;
      localPipelineDirty.current = true;
      setPipeline(nextPipeline);
      if (collabDoc.current) setPipelineDoc(collabDoc.current, nextPipeline);
      setFlowNodes((nodes) => nodes.map((node) => node.id === selected ? { ...node, data: { ...node.data, label: config.name || config.table || selectedModel?.type || node.data.label } } : node));
      if (projectId) {
        try {
          const saved = await api.savePipeline(projectId, nextPipeline);
          pipelineRef.current = saved;
          setPipeline(saved);
          setProjectMessage("Configuration saved");
        } catch (cause: unknown) {
          setError(cause instanceof Error ? cause.message : "Unable to save pipeline");
        }
      }
    } catch {
      setError("Inspector configuration must be valid JSON");
    }
  };

  const validate = async () => {
    if (!projectId) return;
    try {
      const result = await api.validate(projectId);
      setProblems(result.problems);
      setValidation(result.valid ? "Pipeline is valid" : result.problems.map((problem) => `${problem.code}: ${problem.message}`).join("\n"));
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : "Validation failed";
      setProblems([{ code: "SDPS-CLIENT-VALIDATION-001", severity: "error", message }]);
      setValidation(message);
    }
  };

  const inspectPlan = async () => {
    if (!projectId) return;
    try {
      const capturedRun = runsRef.current.find((run) => ["succeeded", "completed"].includes(String(run.status)));
      if (capturedRun) {
        setProjectMessage(`Plan Inspector: captured Spark plan from run ${capturedRun.id}`);
        setDebugPlan(JSON.stringify(await api.runPlan(capturedRun.id), null, 2));
        return;
      }
      setProjectMessage("Plan Inspector: pre-run advisory (no captured run plan available)");
      setDebugPlan(JSON.stringify(await api.debugPlan(projectId), null, 2));
    }
    catch (cause: unknown) { setDebugPlan(cause instanceof Error ? cause.message : "Plan inspection failed"); }
  };

  const inspectRowTrace = async () => {
    if (!projectId || !selected) return;
    try { const result = await api.rowTrace(projectId, selected, previewRows); setProjectMessage(result.execution_backed ? "Row Trace reflects persisted run execution" : "Row Trace uses caller-supplied sample rows"); setRowTrace(JSON.stringify(result, null, 2)); }
    catch (cause: unknown) { setRowTrace(cause instanceof Error ? cause.message : "Row trace failed"); }
  };

  const evaluateSelectedQuality = async () => {
    if (!projectId || !selected || !selectedModel?.type.startsWith("quality.")) return;
    try { setQualityResult(JSON.stringify(await api.evaluateQuality(projectId, selected, previewRows), null, 2)); }
    catch (cause: unknown) { setQualityResult(cause instanceof Error ? cause.message : "Quality evaluation failed"); }
  };

  const compareRecentRuns = async () => {
    if (!projectId || runs.length < 2) return;
    try { setRunComparison(JSON.stringify(await api.compareRuns(projectId, runs[1].id, runs[0].id), null, 2)); }
    catch (cause: unknown) { setRunComparison(cause instanceof Error ? cause.message : "Run comparison failed"); }
  };

  const compareSelectedRuns = async (leftRunId: string, rightRunId: string) => {
    if (!projectId || leftRunId === rightRunId) return;
    try { setRunComparison(JSON.stringify(await api.compareRuns(projectId, leftRunId, rightRunId), null, 2)); }
    catch (cause: unknown) { setRunComparison(cause instanceof Error ? cause.message : "Run comparison failed"); }
  };

  const generate = async () => {
    if (!projectId) return;
    setGeneratedLanguage("python");
    setGenerated("Generating…");
    setWorkspaceView("code");
    try {
      const result = await api.generate(projectId);
      const file = result.files.find((item) => item.path.endsWith(".py"));
      setGeneratedLanguage("python");
      setGeneratedSourceMap((result.source_map || []) as SourceMapEntry[]);
      const source = file?.content || (result.problems ?? []).map((problem) => `${problem.code}: ${problem.message}`).join("\n");
      setGenerated(source);
      if (collabDoc.current) setSourceText(collabDoc.current, "python", source);
    } catch (cause: unknown) {
      setGenerated(cause instanceof Error ? cause.message : "Generation failed");
    }
  };

  const generateSql = async () => {
    if (!projectId) return;
    setGeneratedLanguage("sql");
    setGenerated("Generating…");
    setWorkspaceView("code");
    try {
      const result = await api.generateSql(projectId);
      setGeneratedLanguage("sql");
      setGeneratedSourceMap((result.source_map || []) as SourceMapEntry[]);
      const source = result.files.map((file) => file.content).join("\n") || (result.problems ?? []).map((problem) => `${problem.code}: ${problem.message}`).join("\n");
      setGenerated(source);
      if (collabDoc.current) setSourceText(collabDoc.current, "sql", source);
    } catch (cause: unknown) {
      setGenerated(cause instanceof Error ? cause.message : "SQL generation failed");
    }
  };

  const reconcileGenerated = async () => {
    if (!projectId || !generated) return;
    try {
      const result = generatedLanguage === "python" ? await api.reconcilePython(projectId, generated) : await api.reconcileSql(projectId, generated);
      setProblems(result.problems.map((problem) => ({
        code: problem.code,
        severity: "error",
        message: problem.message,
        line: problem.line ?? null,
      })));
      setProjectMessage(result.ownership === "visual" ? (result.changed ? "Generated source reconciled into the visual graph" : "Generated source matches the visual graph") : `Source kept custom-owned: ${result.problems[0]?.code || "unsupported edit"}`);
      if (result.changed) {
        setPipeline(result.document);
        setFlowNodes(result.document.nodes.map((node) => { const operator = operators.find((item) => item.id === node.type); return { id: node.id, position: node.position, data: visualNodeData(node, operator), type: "generic" }; }));
        setFlowEdges(result.document.edges.map((edge) => ({ id: edge.id, source: edge.from.node, target: edge.to.node, label: edge.to.port })));
      }
    } catch (cause: unknown) { setProjectMessage(cause instanceof Error ? cause.message : "Reconciliation failed"); }
  };

  const setAuthToken = () => setShowAuthPanel((visible) => !visible);

  const run = async (mode: "incremental" | "refresh" | "full-refresh" | "full-refresh-all" = "incremental") => {
    if (!projectId) return;
    try {
      const selectedTargets = selected ? [selected] : [];
      const result = await api.run(projectId, mode, mode === "incremental" || mode === "full-refresh-all" ? [] : selectedTargets, runtimeProfileId || undefined);
      setActiveRunId(result.id || null);
      setRunStatus(`${result.status}${result.id ? ` · ${result.id}` : ""}${result.error ? `: ${result.error}` : ""}`);
      setRuns(await api.runs(projectId));
      if (result.id) await refreshExecutionHealth(result.id);
    } catch (cause: unknown) {
      setRunStatus(cause instanceof Error ? cause.message : "Run submission failed");
    }
  };

  const refreshExecutionHealth = useCallback(async (runId: string) => {
    try {
      const detail = await api.runDetail(runId);
      if (isTerminalRunStatus(detail.status)) {
        setActiveRunId((current) => current === runId ? null : current);
      }
      const progressEvents = detail.events.filter((event) => event.kind === "query_progress" || event.data?.query_id);
      if (progressEvents.length) {
        setStreamingDiagnostics(await api.streamingDiagnostics(progressEvents.map((event) => event.data || event)));
      } else {
        setStreamingDiagnostics(null);
      }
      const diagnostic = [...detail.events].reverse().find((event) => Array.isArray(event.data?.stages));
      const stages = Array.isArray(diagnostic?.data?.stages) ? diagnostic.data.stages as Array<Record<string, unknown>> : [];
      setExecutionStages(stages);
      const severe = stages.filter((stage) => Number(stage.skew_score || 0) >= 5).length;
      const moderate = stages.filter((stage) => Number(stage.skew_score || 0) >= 2).length;
      const health = severe ? "severe" : moderate ? "moderate" : stages.length ? "healthy" : undefined;
      if (health) setFlowNodes((nodes) => nodes.map((node) => {
        const stage = stages.find((candidate) => String(candidate.node_id || candidate.node || "") === node.id);
        const metrics = stage ? {
          duration: Number(stage.max_task_ms || stage.duration_ms || 0),
          rows: Number(stage.output_rows || stage.input_rows || 0),
          bytes: Number(stage.output_bytes || 0),
          shuffle: Number(stage.shuffle_read_bytes || 0) + Number(stage.shuffle_write_bytes || 0),
          skew: Number(stage.skew_score || 0),
        } : node.data?.metrics;
        return { ...node, data: { ...node.data, health, metrics, healthDetail: `${stages.length} Spark stage${stages.length === 1 ? "" : "s"} · ${severe} severe` } };
      }));
      if (!stages.length) {
        setExecutionHealth(`Run ${detail.status}; Spark stage metrics are not available yet.`);
        return;
      }
      setExecutionHealth(`Run ${detail.status} · ${stages.length} stages · ${severe} severe skew stage${severe === 1 ? "" : "s"}`);
    } catch (cause: unknown) {
      setExecutionHealth(cause instanceof Error ? cause.message : "Execution health unavailable");
    }
  }, [setFlowNodes]);

  const testRuntimeProfile = async () => {
    if (!runtimeProfileId) return;
    try {
      const result = await api.testRuntimeProfile(runtimeProfileId);
      setRuntimeProfileMessage(result.available ? `Available · ${String(result.adapter || "runtime")}` : "Unavailable");
    } catch (cause: unknown) {
      setRuntimeProfileMessage(cause instanceof Error ? cause.message : "Runtime profile test failed");
    }
  };
  const saveEnvironmentMapping = async (environment: Record<string, string>) => {
    if (!runtimeProfileId) return;
    try { const profile = runtimeProfiles.find((item) => item.id === runtimeProfileId); if (!profile) return; const updated = await api.updateRuntimeProfile(runtimeProfileId, { config: { ...profile.config, environment } }); setRuntimeProfiles((current) => current.map((item) => item.id === updated.id ? updated : item)); setRuntimeProfileMessage("Environment mapping saved"); }
    catch (cause: unknown) { setRuntimeProfileMessage(cause instanceof Error ? cause.message : "Unable to save environment mapping"); }
  };

  const saveRuntimeConfig = async (config: Record<string, unknown>) => {
    if (!runtimeProfileId) return;
    try { const updated = await api.updateRuntimeProfile(runtimeProfileId, { config }); setRuntimeProfiles((current) => current.map((item) => item.id === updated.id ? updated : item)); setRuntimeProfileMessage("Runtime settings saved"); }
    catch (cause) { setRuntimeProfileMessage(cause instanceof Error ? cause.message : "Unable to save runtime settings"); }
  };

  const updateParameter = (nodeId: string, config: Record<string, unknown>) => {
    if (!projectId) return;
    const updated = { ...pipeline, nodes: pipeline.nodes.map((node) => node.id === nodeId ? { ...node, config } : node) };
    pipelineRef.current = updated;
    setPipeline(updated);
    void api.savePipeline(projectId, updated).catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to save parameter"));
  };

  const createRuntimeProfile = async () => {
    const name = window.prompt("Runtime profile name");
    const adapter = window.prompt("Adapter", "local");
    if (!name?.trim() || !adapter?.trim()) return;
    try {
      const profile = await api.createRuntimeProfile({ name: name.trim(), adapter: adapter.trim(), config: {} });
      setRuntimeProfiles((current) => [...current, profile]);
      setRuntimeProfileId(profile.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to create runtime profile"); }
  };

  const deleteRuntimeProfile = async () => {
    if (!runtimeProfileId || !window.confirm("Delete this runtime profile?")) return;
    try {
      await api.deleteRuntimeProfile(runtimeProfileId);
      setRuntimeProfiles((current) => current.filter((profile) => profile.id !== runtimeProfileId));
      setRuntimeProfileId("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to delete runtime profile"); }
  };

  const cancelRun = async () => {
    if (!activeRunId) return;
    try {
      const result = await api.cancelRun(activeRunId);
      setRunStatus(result.cancelled ? `cancelled · ${activeRunId}` : `run already finished · ${activeRunId}`);
      if (result.cancelled) setActiveRunId(null);
    } catch (cause: unknown) {
      setRunStatus(cause instanceof Error ? cause.message : "Run cancellation failed");
    }
  };

  const downloadDebugBundle = async (runId: string) => {
    try {
      const manifestResponse = await fetch(`/api/runs/${encodeURIComponent(runId)}/debug-bundle/preview`, { credentials: "same-origin" });
      if (!manifestResponse.ok) throw new Error(`Unable to preview debug bundle (${manifestResponse.status})`);
      const manifest = await manifestResponse.json() as Record<string, unknown>;
      setDebugBundleManifest(manifest);
      const files = Array.isArray(manifest.files) ? manifest.files.length : 0;
      if (!window.confirm(`Export redacted debug bundle with ${files} files?`)) return;
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/debug-bundle`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`Unable to export debug bundle (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `sdpstudio-debug-${runId}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Debug-bundle export failed");
    }
  };

  const refreshGit = async () => {
    if (!projectId) return;
    try {
      const [status, diff, tags, stashes, conflicts, branches, log, remotes] = await Promise.all([api.gitStatus(projectId), api.gitDiff(projectId), api.gitTags(projectId), api.gitStash(projectId), api.gitConflicts(projectId), api.gitBranches(projectId), api.gitLog(projectId), api.gitRemotes(projectId)]);
      setGitStatus(status);
      setGitRemotes(remotes);
      setGitBranches(branches);
      setGitLog(log);
      setGitDiff(diff.diff);
      setGitTags(tags);
      setGitStashes(stashes);
      setGitConflicts(conflicts);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Git status failed");
    }
  };

  const syncGit = async (operation: "fetch" | "pull" | "push") => {
    if (!projectId) return;
    try {
      const remote = Object.keys(gitRemotes)[0] || "origin";
      const branch = gitBranches.current || undefined;
      const status = operation === "fetch" ? await api.gitFetch(projectId, remote) : operation === "pull" ? await api.gitPull(projectId, remote, branch) : await api.gitPush(projectId, remote, branch);
      setGitStatus(status);
      await refreshGit();
    } catch (cause) { setError(cause instanceof Error ? cause.message : `Git ${operation} failed`); }
  };

  const createGitBranch = async () => {
    if (!projectId) return;
    const name = window.prompt("New branch name");
    if (!name?.trim()) return;
    try { setGitBranches(await api.createGitBranch(projectId, name.trim())); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to create branch"); }
  };

  const switchGitBranch = async (name: string) => {
    if (!projectId || name === gitBranches.current) return;
    try { setGitBranches(await api.switchGitBranch(projectId, name)); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to switch branch"); }
  };

  const deleteGitBranch = async () => {
    if (!projectId || !gitBranches.current || gitBranches.current === "main") return;
    if (!window.confirm(`Delete branch ${gitBranches.current}?`)) return;
    try { setGitBranches(await api.deleteGitBranch(projectId, gitBranches.current)); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to delete branch"); }
  };

  const commitGit = async () => {
    if (!projectId || !commitMessage.trim()) return;
    try {
      await api.gitStage(projectId);
      setGitStatus(await api.gitCommit(projectId, commitMessage.trim()));
      setCommitMessage("");
      await refreshGit();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Git commit failed");
    }
  };

  const createGitTag = async () => {
    if (!projectId) return;
    const name = window.prompt("Tag name");
    if (!name?.trim()) return;
    try { setGitTags(await api.createGitTag(projectId, name.trim())); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git tag failed"); }
  };

  const createGitStash = async () => {
    if (!projectId) return;
    const message = window.prompt("Stash message", "SDP Studio changes") || undefined;
    try { await api.gitStashAction(projectId, "create", message); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git stash failed"); }
  };

  const applyGitStash = async () => {
    if (!projectId || gitStashes.length === 0) return;
    try { await api.gitStashAction(projectId, "apply"); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git stash apply failed"); }
  };

  const stageGit = async () => {
    if (!projectId) return;
    try { setGitStatus(await api.gitStage(projectId)); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git stage failed"); }
  };

  const stageGitPath = async (path: string) => {
    if (!projectId) return;
    try { setGitStatus(await api.gitStage(projectId, [path])); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git path staging failed"); }
  };

  const unstageGitPath = async (path: string) => {
    if (!projectId) return;
    try { setGitStatus(await api.gitUnstage(projectId, [path])); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git path unstaging failed"); }
  };

  const unstageGit = async () => {
    if (!projectId) return;
    try { setGitStatus(await api.gitUnstage(projectId)); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git unstage failed"); }
  };

  const resolveGitConflict = async (path: string, strategy: "ours" | "theirs") => {
    if (!projectId) return;
    try { await api.resolveGitConflict(projectId, path, strategy); await refreshGit(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git conflict resolution failed"); }
  };

  const previewGitConflict = async (path: string) => {
    if (!projectId) return;
    try { const versions = await api.gitConflictVersions(projectId, path); setGitConflictPreview({ path, ...versions }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Git conflict preview failed"); }
  };

  const loadGitReviews = async () => {
    if (!projectId) return;
    try { setGitReviews(await api.gitReviews(projectId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load provider reviews"); }
  };

  const loadGitRepository = async () => {
    if (!projectId) return;
    try { setGitRepository(await api.gitRepository(projectId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load repository metadata"); }
  };

  const createGitReview = async () => {
    if (!projectId) return;
    const title = window.prompt("Review title");
    const head = window.prompt("Head branch");
    if (!title?.trim() || !head?.trim()) return;
    const base = window.prompt("Base branch", "main") || "main";
    try {
      const review = await api.createGitReview(projectId, { title: title.trim(), body: "", head: head.trim(), base });
      setGitReviews((current) => [review, ...current]);
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to create provider review"); }
  };

  const previewNode = async (forceRefresh = false) => {
    if (!projectId || !selected) return;
    const confirmSinkTest = selectedModel?.type.startsWith("sink.") ? window.confirm("This preview targets a sink and may have side effects. Continue?") : false;
    if (selectedModel?.type.startsWith("sink.") && !confirmSinkTest) return;
    try {
      const result = await api.preview(projectId, selected, previewLimit, { include_profile: previewIncludeProfile, include_plan: previewIncludePlan, sampling_fraction: previewSamplingFraction, seed: previewSeed, timeout_seconds: previewTimeout, cache_ttl_seconds: previewCacheTtl, force_refresh: forceRefresh || previewForceRefresh, confirm_sink_test: confirmSinkTest });
      setPreviewForceRefresh(false);
      setPreviewResult(result);
      setPreviewRows(result.rows);
      setPreview(JSON.stringify(result.rows, null, 2));
      setProfile(JSON.stringify(result.profile || { message: "Runtime profile unavailable" }, null, 2));
    } catch (cause: unknown) {
      setPreviewResult(null); setPreview(cause instanceof Error ? cause.message : "Preview failed");
    }
  };

  const createProject = async (sampleName?: string, example?: string) => {
    const name = sampleName || `pipeline-${new Date().toISOString().slice(0, 10)}-${crypto.randomUUID().slice(0, 8)}`;
    try {
      const created = await api.createProject(name, example);
      setProjectMessage(`Created ${created.name}`);
      setProjects((current) => [...current, created]);
      await selectProject(created.id);
    } catch (cause: unknown) {
      setProjectMessage(cause instanceof Error ? cause.message : "Project creation failed");
    }
  };

  const cloneProject = async () => {
    const remoteUrl = window.prompt("Git repository URL");
    if (!remoteUrl?.trim()) return;
    const name = window.prompt("Project name", `clone-${new Date().toISOString().slice(0, 10)}`);
    if (!name?.trim()) return;
    const branch = window.prompt("Branch (optional)", "") || undefined;
    try {
      const cloned = await api.cloneProject(name.trim(), remoteUrl.trim(), branch?.trim() || undefined);
      setProjects((current) => [...current, cloned]);
      await selectProject(cloned.id);
      setProjectMessage("Project cloned");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Unable to clone project");
    }
  };

  const createSchedule = async (payload: { name: string; cron: string; timezone: string; mode: string; runtime_profile_id?: string; concurrency_policy?: string; missed_run_policy?: string } = { name: "daily", cron: "0 0 * * *", timezone: "UTC", mode: "incremental", concurrency_policy: "skip", missed_run_policy: "skip" }) => {
    if (!projectId) return;
    try {
      const created = await api.createSchedule(projectId, payload);
      setSchedules((current) => [...current, created]);
      setShowScheduleForm(false);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Schedule creation failed");
    }
  };

  const toggleSchedule = async (schedule: Schedule) => {
    try {
      const updated = await api.toggleSchedule(schedule.id, !schedule.enabled);
      setSchedules((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Schedule update failed");
    }
  };

  const runScheduleNow = async (schedule: Schedule) => {
    if (!projectId) return;
    try {
      const result = await api.runScheduleNow(projectId, schedule.id);
      setActiveRunId(result.id);
      setRunStatus(`submitted · ${result.id}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Schedule run failed"); }
  };

  const deleteSchedule = async (schedule: Schedule) => {
    if (!window.confirm(`Delete schedule ${schedule.name}?`)) return;
    try { await api.deleteSchedule(schedule.id); setSchedules((current) => current.filter((item) => item.id !== schedule.id)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Schedule deletion failed"); }
  };

  const focusGeneratedRegion = (mapping: SourceMapEntry) => {
    setGeneratedLanguage(mapping.file?.endsWith(".sql") ? "sql" : "python");
    setActiveSection("code");
    document.querySelector(".code-panel")?.scrollIntoView({ behavior: "smooth", block: "center" });
    const line = Math.max(1, mapping.start_line);
    const column = Math.max(1, mapping.start_column || 1);
    generatedEditor.current?.revealLineInCenter(line);
    generatedEditor.current?.setPosition({ lineNumber: line, column });
    generatedEditor.current?.setSelection({
      startLineNumber: line,
      startColumn: column,
      endLineNumber: Math.max(line, mapping.end_line),
      endColumn: Math.max(column, mapping.end_column || column),
    });
    generatedEditor.current?.focus();
  };

  useEffect(() => {
    if (!activeRunId) return;
    void refreshExecutionHealth(activeRunId);
    const timer = window.setInterval(() => void refreshExecutionHealth(activeRunId), 2000);
    return () => window.clearInterval(timer);
  }, [activeRunId, refreshExecutionHealth]);

  const quickStartAction = async (step: QuickStartStep) => {
    if (step.id === "sample") await createProject("retail-etl", "retail-etl");
    else if (step.id === "runtime") setActiveSection("settings");
    else if (step.id === "design") setActiveSection("canvas");
    else if (step.id === "generate") await generate();
    else if (step.id === "validate") await validate();
    else if (step.id === "dry-run") await previewNode();
    else if (step.id === "run") await run();
    else if (step.id === "debug") { setActiveSection("debug"); await inspectPlan(); }
  };

  const dismissQuickStart = () => {
    window.localStorage.setItem("sdpstudio.quick-start.completed", "1");
    setShowQuickStart(false);
  };
  const selectedPresenceNodes = presenceStates
    .map((state) => state.selected_node_id)
    .filter((nodeId): nodeId is string => Boolean(nodeId))
    .slice(0, 3);
  const overlayNodes = flowNodes.map((node) => {
    if (!metricOverlay) return { ...node, data: { ...node.data, onSelect: () => chooseNode(node.id) } };
    const metrics = node.data?.metrics as Record<string, string | number> | undefined;
    return { ...node, data: { ...node.data, onSelect: () => chooseNode(node.id), overlayMetric: metricOverlay, overlayValue: metrics?.[metricOverlay] ?? "unavailable" } };
  });

  return (
    <main className="shell" aria-labelledby="title" data-workspace-view={workspaceView}>
      <header className="shell-header">
        <div>
          <p className="eyebrow">Apache Spark Declarative Pipelines</p>
          <h1 id="title">SDP Studio</h1>
        </div>
        <div className="header-actions"><select className="project-select" aria-label="Project" value={projectId || ""} onChange={(event) => void selectProject(event.target.value)}><option value="" disabled>Select project</option>{projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select><button className="new-project" onClick={() => void createProject()}>New project</button><button className="validate" onClick={() => void validate()}>Validate</button><button className="generate" onClick={() => void generate()}>Python</button><button className="generate" onClick={() => void generateSql()}>SQL</button><button className="run" onClick={() => void run()}>Run</button><button className="run" onClick={() => void run("refresh")}>Refresh selected</button><button className="run" onClick={() => void run("full-refresh")}>Full refresh selected</button><button className="run" onClick={() => void run("full-refresh-all")}>Full refresh all</button>{activeRunId && <button className="cancel" onClick={() => void cancelRun()}>Cancel run</button>}<button className="new-project" onClick={setAuthToken}>Auth</button><span className="presence" aria-label="Collaborators">{presence} collaborator{presence === 1 ? "" : "s"}</span>{selectedPresenceNodes.length > 0 && <span className="presence-selection" aria-label={`Collaborators editing ${selectedPresenceNodes.join(", ")}`}>editing {selectedPresenceNodes.join(", ")}</span>}<span className={`status ${runtime?.available ? "ready" : "warning"}`}>{runtime ? `${runtime.available ? "Spark ready" : "Spark unavailable"}${runtime.spark_version ? ` · ${runtime.spark_version}` : ""}` : "Checking Spark…"}</span></div>
        <button className="new-project" onClick={() => void cloneProject()}>Clone project</button>
      </header>
      {showAuthPanel && <AuthPanel onToken={() => window.location.reload()} onIdentity={(identity) => setAuthRole(identity?.role || null)} />}
      {showQuickStart && <QuickStartWizard onAction={quickStartAction} onDismiss={dismissQuickStart} />}
      <button className="preview" onClick={() => setShowScheduleForm((current) => !current)}>Create schedule</button>{showScheduleForm && <ScheduleForm onSubmit={(payload) => void createSchedule(payload)} onCancel={() => setShowScheduleForm(false)} />}
      {runs.length > 1 && <RunComparisonSelector runs={runs} onCompare={(left, right) => void compareSelectedRuns(left, right)} />}{runComparison && <RunComparisonPanel value={runComparison} />}{debugBundleManifest && <section aria-label="Debug bundle redaction preview"><h3>Debug bundle redaction preview</h3><p className="muted">The bundle will contain {Array.isArray(debugBundleManifest.files) ? debugBundleManifest.files.length : 0} redacted files.</p><pre className="generated">{JSON.stringify(debugBundleManifest, null, 2)}</pre></section>}
      {activeRunId && runtimeProfileId && runtimeProfiles.find((profile) => profile.id === runtimeProfileId)?.adapter === "kubernetes" && <KubernetesRunPanel runId={activeRunId} />}
      <GitGraphDiffPanel projectId={projectId} />
      {generatedSourceMap.length > 0 && <section className="source-map-panel" aria-label="Generated source map"><h3>Node source regions</h3>{generatedSourceMap.map((mapping, index) => <button className="run-row source-map-entry" key={`${mapping.node_id || "region"}-${index}`} onClick={() => focusGeneratedRegion(mapping)}><code>{mapping.node_id || "generated"}</code><small>{mapping.file || generatedLanguage} lines {mapping.start_line}–{mapping.end_line}</small></button>)}</section>}
      <section className="git-sync" aria-label="Git synchronization"><button className="preview" onClick={() => void syncGit("fetch")} disabled={!projectId}>Fetch</button><button className="preview" onClick={() => void syncGit("pull")} disabled={!projectId}>Pull</button><button className="preview" onClick={() => void syncGit("push")} disabled={!projectId}>Push</button></section>
      {gitStatus?.entries.length ? <section className="git-files" aria-label="Changed files"><h3>Changed files</h3>{gitStatus.entries.map((entry) => { const path = entry.slice(3).trim(); const staged = entry[0] !== " " && entry[0] !== "?"; return <div className="run-row" key={entry}><code>{path}</code>{staged ? <button className="preview" onClick={() => void unstageGitPath(path)}>Unstage</button> : <button className="preview" onClick={() => void stageGitPath(path)}>Stage</button>}</div>; })}</section> : null}
      {gitConflictPreview && <section className="git-conflict-preview" aria-label="Conflict preview"><h3>{gitConflictPreview.path}</h3><div><strong>Ours</strong><pre>{gitConflictPreview.ours}</pre></div><div><strong>Theirs</strong><pre>{gitConflictPreview.theirs}</pre></div><button className="preview" onClick={() => setGitConflictPreview(null)}>Close preview</button></section>}
      {gitConflicts.length > 0 && <section className="git-conflict-previews" aria-label="Conflict files"><h3>Conflict files</h3>{gitConflicts.map((path) => <button className="preview" key={`preview-${path}`} onClick={() => void previewGitConflict(path)}>Preview {path}</button>)}</section>}
      {rowTrace && <RowTracePanel value={rowTrace} />}
      {selectedModel?.type.startsWith("quality.") && <section className="quality-panel" aria-label="Quality evaluation"><button className="preview" onClick={() => void evaluateSelectedQuality()}>Evaluate quality</button>{qualityResult && <pre className="generated" aria-label="Quality result">{qualityResult}</pre>}</section>}
      {previewResult && <PreviewTable result={previewResult} />}
      <section className="preview-controls" aria-label="Preview controls"><h3>Preview controls</h3><label>Rows<input aria-label="Preview row limit" type="number" min="1" max="200" value={previewLimit} onChange={(event) => setPreviewLimit(Math.max(1, Math.min(200, Number(event.target.value) || 1)))} /></label><label>Sampling fraction<input aria-label="Sampling fraction" type="number" min="0.01" max="1" step="0.01" value={previewSamplingFraction} onChange={(event) => setPreviewSamplingFraction(Math.max(0.01, Math.min(1, Number(event.target.value) || 0.01)))} /></label><label>Seed<input aria-label="Sampling seed" type="number" min="0" value={previewSeed} onChange={(event) => setPreviewSeed(Math.max(0, Number(event.target.value) || 0))} /></label><label>Timeout (seconds)<input aria-label="Preview timeout" type="number" min="1" max="600" value={previewTimeout} onChange={(event) => setPreviewTimeout(Math.max(1, Math.min(600, Number(event.target.value) || 1)))} /></label><label>Cache TTL (seconds)<input aria-label="Preview cache TTL" type="number" min="0" max="86400" value={previewCacheTtl} onChange={(event) => setPreviewCacheTtl(Math.max(0, Math.min(86400, Number(event.target.value) || 0)))} /></label><button className="preview" onClick={() => void previewNode(true)} disabled={!selected}>Refresh preview now</button><label><input aria-label="Include profile" type="checkbox" checked={previewIncludeProfile} onChange={(event) => setPreviewIncludeProfile(event.target.checked)} /> Include profile</label><label><input aria-label="Include plan" type="checkbox" checked={previewIncludePlan} onChange={(event) => setPreviewIncludePlan(event.target.checked)} /> Include plan</label></section>
      <nav className="editor-toolbar" aria-label="Edit history"><button className="preview" onClick={undo} disabled={historyDepth === 0}>Undo</button><button className="preview" onClick={redo} disabled={futureDepth === 0}>Redo</button><button className="preview" onClick={autoLayout} disabled={flowNodes.length === 0}>Auto-layout</button><span className="muted">Ctrl/Cmd+Z · Ctrl/Cmd+Y</span></nav>
      <section className="metric-overlays" aria-label="Debug metric overlays"><h3>Canvas metrics</h3><select aria-label="Metric overlay" value={metricOverlay || ""} onChange={(event) => setMetricOverlay((event.target.value || null) as MetricOverlay | null)}><option value="">None</option>{(["duration", "rows", "bytes", "shuffle", "skew", "quality", "freshness", "compatibility"] as MetricOverlay[]).map((metric) => <option value={metric} key={metric}>{metric}</option>)}</select>{metricOverlay && <p className="muted">Showing {metricOverlay}; unavailable values indicate that the selected run did not capture this metric.</p>}</section>
      <ActivityRail activeSection={activeSection} onSelect={setActiveSection} theme={theme} onToggleTheme={() => setThemeChoice((current) => current === "dark" ? "light" : current === "light" ? "system" : "dark")} commands={[{ id: "validate", label: "Validate pipeline", run: () => void validate() }, { id: "generate-python", label: "Generate Python", run: () => void generate() }, { id: "generate-sql", label: "Generate SQL", run: () => void generateSql() }, { id: "run", label: "Run pipeline", run: () => void run() }]} />
      <ProblemsPanel problems={problems} onSelectNode={chooseNode} />
      {selected && <SchemaInspector fields={selectedOperator?.fields || []} value={configText} onChange={setConfigText} />}
      <ParameterEditor parameters={pipeline.nodes.filter((node) => node.type === "utility.parameter").map((node) => ({ id: node.id, config: node.config }))} onChange={updateParameter} />
      <GraphOutline nodes={flowNodes.map((node) => ({ id: node.id, label: String(node.data?.label || ""), operatorId: String(node.data?.operatorId || "") }))} edges={flowEdges.map((edge) => ({ source: edge.source, target: edge.target }))} />
      <WorkspaceTabs active={workspaceView} onChange={setWorkspaceView} />
      <WorkspaceLayoutControls value={workspaceLayout} onChange={setWorkspaceLayout} />
      <section className="extensions-panel" aria-label="Extensions"><h3>Extensions</h3><p className="muted">Installed operator, runtime, Git, catalog, importer, and diagnostic extensions are discovered from the server capability inventory.</p></section>
      <section className="workspace" aria-label="Pipeline workspace"><RuntimeProfilePanel profiles={runtimeProfiles} value={runtimeProfileId} onChange={(value) => { setRuntimeProfileId(value); setRuntimeProfileMessage(null); }} onTest={() => void testRuntimeProfile()} onSaveEnvironment={(environment) => void saveEnvironmentMapping(environment)} onSaveConfig={saveRuntimeConfig} message={runtimeProfileMessage} /><section className="runtime-management" aria-label="Runtime profile management"><button className="preview" onClick={() => void createRuntimeProfile()}>Create runtime profile</button><button className="preview" onClick={() => void deleteRuntimeProfile()} disabled={!runtimeProfileId}>Delete selected profile</button></section>
        <aside className="palette"><h2>Operators</h2><input aria-label="Search operators" placeholder="Search operators" value={operatorQuery} onChange={(event) => setOperatorQuery(event.target.value)} />{error && <p role="alert">{error}</p>}{Object.entries(groupedOperators).sort(([a], [b]) => a.localeCompare(b)).map(([category, items]) => <section className="operator-group" aria-label={`${category} operators`} key={category}><h3>{category}</h3>{items.sort((a, b) => a.title.localeCompare(b.title)).map((operator) => { const unavailable = operatorAvailability(operator); return <button className="operator" key={operator.id} draggable={!unavailable} disabled={Boolean(unavailable)} title={unavailable || undefined} aria-label={unavailable ? `${operator.title} unavailable: ${unavailable}` : operator.title} onDragStart={(event) => event.dataTransfer.setData("application/x-sdpstudio-operator", operator.id)} onClick={() => addOperator(operator)}>{operator.title}<small>{unavailable || operator.category}</small></button>; })}</section>)}</aside>
        <section className="git-panel" aria-label="Git"><h2>Git</h2><p className="muted">{gitStatus?.initialized ? `${gitStatus.branch || "detached"} · ${gitStatus.dirty ? "dirty" : "clean"}` : "Repository not initialized"}</p><button className="preview" onClick={() => void refreshGit()}>Refresh Git status</button><input aria-label="Git commit message" value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} placeholder="Commit message" /><button className="preview" onClick={() => void commitGit()} disabled={!commitMessage.trim()}>Commit changes</button>{gitDiff && <pre className="generated" aria-label="Git diff">{gitDiff}</pre>}<section className="git-branches" aria-label="Git branches"><h3>Branches</h3><button className="preview" onClick={() => void createGitBranch()}>Create branch</button><button className="preview" onClick={() => void deleteGitBranch()} disabled={!gitBranches.current || gitBranches.current === "main"}>Delete selected branch</button><select aria-label="Git branch" value={gitBranches.current || ""} onChange={(event) => void switchGitBranch(event.target.value)}>{gitBranches.branches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}</select></section><section className="git-log" aria-label="Git history"><h3>History</h3>{gitLog.slice(0, 8).map((entry) => <div className="run-row" key={entry.commit}><span>{entry.subject}</span><small>{entry.commit.slice(0, 8)} · {entry.author}</small></div>)}</section><section className="git-remotes" aria-label="Git remotes"><h3>Remotes</h3>{Object.entries(gitRemotes).map(([name, url]) => <div className="run-row" key={name}><span>{name}</span><small>{url}</small></div>)}</section></section>
        <section className="git-tools" aria-label="Git tags and stash"><h3>Tags and stash</h3><button className="preview" onClick={() => void createGitTag()}>Create tag</button><button className="preview" onClick={() => void createGitStash()}>Stash changes</button><button className="preview" onClick={() => void applyGitStash()} disabled={gitStashes.length === 0}>Apply latest stash</button><small>{gitTags.length} tags · {gitStashes.length} stashes</small></section>
        <section className="git-index" aria-label="Git staging"><h3>Index and conflicts</h3><button className="preview" onClick={() => void stageGit()}>Stage all</button><button className="preview" onClick={() => void unstageGit()}>Unstage all</button><small>{gitConflicts.length ? `${gitConflicts.length} conflicts` : "No conflicts"}</small>{gitConflicts.map((path) => <div className="run-row" key={path}><code>{path}</code><button className="preview" onClick={() => void resolveGitConflict(path, "ours")}>Use ours</button><button className="preview" onClick={() => void resolveGitConflict(path, "theirs")}>Use theirs</button></div>)}</section>
        <section className="git-reviews" aria-label="Provider reviews"><h3>Provider reviews</h3><button className="preview" onClick={() => void loadGitRepository()}>Load repository</button><button className="preview" onClick={() => void loadGitReviews()}>Load reviews</button><button className="preview" onClick={() => void createGitReview()}>Create review</button>{gitRepository && <div className="run-row"><span>{gitRepository.full_name || gitRepository.name || "Repository"}</span><small>{gitRepository.default_branch ? `default: ${gitRepository.default_branch}` : ""}{(gitRepository.html_url || gitRepository.web_url) && <> · <a href={gitRepository.html_url || gitRepository.web_url} target="_blank" rel="noreferrer">Open provider</a></>}</small></div>}{gitReviews.slice(0, 5).map((review, index) => <div className="run-row" key={review.id || `${review.title}-${index}`}><span>{review.title || "Untitled review"}</span><small>{review.state || "unknown"}{review.url && <> · <a href={review.url} target="_blank" rel="noreferrer">Open review</a></>}</small></div>)}</section>
        <section className="catalog-panel" aria-label="Catalog"><h3>Catalog</h3><button className="preview" onClick={() => void loadCatalog()}>Load catalog</button>{catalog && <><small>{catalog.namespace} · {catalog.tables.length} tables</small>{catalog.tables.slice(0, 8).map((table) => <div className="run-row" key={table.path}><span>{table.name}</span><small>{table.format}</small></div>)}</>}</section>
        <section className="explorer-panel" aria-label="Explorer"><h3>Explorer</h3><button className="preview" onClick={() => void loadProjectFiles()}>Load project files</button>{projectFiles.slice(0, 30).map((file) => <code key={file.path}>{file.path}</code>)}<FileEditor projectId={projectId} files={projectFiles} collaborativeDoc={activeCollabDoc} onChanged={() => void loadProjectFiles()} /></section>
        <section className="history-panel" aria-label="Local history"><h2>Local history</h2><button className="preview" onClick={() => void createHistoryCheckpoint()}>Create checkpoint</button>{historySnapshots.slice(0, 8).map((snapshot) => <div className="run-row" key={snapshot.id}><span>{snapshot.name || snapshot.reason || "snapshot"}</span><button className="preview" onClick={() => void showHistoryDiff(snapshot.id)}>Diff</button><button className="preview" onClick={() => void restoreHistory(snapshot.id)}>Restore</button></div>)}{historyDiff && <pre className="generated" aria-label="History diff">{historyDiff}</pre>}</section>
        <section className="schedule-actions" aria-label="Schedule actions">{schedules.map((schedule) => <div className="run-row" key={`actions-${schedule.id}`}><button className="preview" onClick={() => void runScheduleNow(schedule)}>Run {schedule.name} now</button><button className="preview" onClick={() => void deleteSchedule(schedule)}>Delete {schedule.name}</button></div>)}</section>
        <div id="workspace-view-canvas" className="canvas" onDragOver={(event) => event.preventDefault()} onDrop={dropOperator} onClick={(event) => { const node = (event.target as HTMLElement).closest("[data-sdp-node-id]"); const nodeId = node?.getAttribute("data-sdp-node-id"); if (nodeId) chooseNode(nodeId); }}><ReactFlow nodes={overlayNodes} edges={flowEdges} nodeTypes={nodeTypes} fitView selectionOnDrag selectNodesOnDrag multiSelectionKeyCode={["Control", "Meta"]} deleteKeyCode={["Backspace", "Delete"]} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={connect} onNodesDelete={deleteNodes} onNodeDragStop={saveDraggedNode} onNodeClick={(event, node) => { event.stopPropagation(); chooseNode(node.id); }} onSelectionChange={({ nodes }) => { const node = nodes[0]; if (node) chooseNode(node.id); }}><Background /><Controls /><MiniMap /></ReactFlow>{flowNodes.length === 0 && !error && <span className="empty">No project pipeline loaded</span>}</div>
        <aside className="inspector"><h2>Inspector</h2>{projectMessage && <p className="muted" role="status">{projectMessage}</p>}{validation && <pre className="validation" role="status">{validation}</pre>}{runStatus && <pre className="validation" role="status">Run: {runStatus}</pre>}<section className="debug-panel" aria-label="Debug tools"><h3>Debug</h3><button className="preview" onClick={() => void inspectPlan()}>Inspect plan</button>{selected && <button className="preview" onClick={() => void inspectRowTrace()}>Row trace</button>}{runs.length > 1 && <button className="preview" onClick={() => void compareRecentRuns()}>Compare recent runs</button>}{debugPlan && <PlanInspector value={debugPlan} />}{rowTrace && <pre className="generated" aria-label="Row trace result">{rowTrace}</pre>}{runComparison && <pre className="generated" aria-label="Run comparison">{runComparison}</pre>}</section><section className="schedules" aria-label="Schedules"><h3>Schedules</h3><button className="preview" onClick={() => void createSchedule()}>Add daily schedule</button>{schedules.map((schedule) => <div className="run-row" key={schedule.id}><span>{schedule.enabled ? "enabled" : "paused"} · {schedule.cron}</span><button className="preview" onClick={() => void toggleSchedule(schedule)}>{schedule.enabled ? "Pause" : "Resume"}</button><small>{schedule.next_fire || "next run unavailable"}</small></div>)}</section>{runs.length > 0 && <section className="runs"><h3>Recent runs</h3>{runs.slice(0, 5).map((item) => <div className="run-row" key={item.id}><span>{item.status}</span><small>{item.id}</small><button className="preview" onClick={() => void downloadDebugBundle(item.id)}>Debug bundle</button></div>)}</section>}{generated && <section className="code-panel" aria-label="Generated source"><h3>Generated {generatedLanguage === "python" ? "Python" : "SQL"}</h3><p className="muted">Edit the source, then reconcile supported changes into the visual graph.</p><button className="preview" onClick={() => void reconcileGenerated()}>Reconcile into graph</button><Editor height="220px" language={generatedLanguage} theme="vs-dark" value={generated} onMount={(editor) => { generatedEditor.current = editor; }} options={{ readOnly: false, minimap: { enabled: false }, wordWrap: "on", fontSize: 11 }} /></section>}{preview && <pre className="generated" aria-label="Preview rows">{preview}</pre>}{profile && <pre className="generated" aria-label="Preview profile">{profile}</pre>}{selected ? <><p className="muted">{selectedOperator?.title || selectedModel?.type}</p><button className="preview" onClick={() => void previewNode()}>Preview rows</button>{selectedOperator?.fields?.map((field) => <label className="field-hint" key={field.name}>{field.label}{field.required ? " *" : ""}</label>)}<textarea aria-label="Node configuration JSON" value={configText} onChange={(event) => setConfigText(event.target.value)} rows={16} /><button className="save-config" onClick={saveConfig}>Save configuration</button></> : <p>Select an operator to edit its configuration.</p>}</aside>
      </section>
      <ExecutionHealthPanel stages={executionStages} />
      {streamingDiagnostics && <section className="execution-health" aria-label="Streaming diagnostics"><h3>Streaming diagnostics</h3><pre className="generated">{JSON.stringify(streamingDiagnostics, null, 2)}</pre></section>}
      <StatusBar projectId={projectId} nodes={flowNodes.length} edges={flowEdges.length} runtimeName={runtimeProfiles.find((item) => item.id === runtimeProfileId)?.name || runtimeProfileId || undefined} collaborators={presence} executionHealth={executionHealth} branch={gitStatus?.branch} dirty={gitStatus?.dirty} />
    </main>
  );
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<StrictMode><ReactFlowProvider><App /></ReactFlowProvider></StrictMode>);
