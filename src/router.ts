const SMART_MODEL = "qwen3:8b";
const FAST_MODEL = "gemma3:4b";

const CODE_SIGNALS = [
  "code",
  "function",
  "class",
  "implement",
  "refactor",
  "debug",
  "algorithm",
  "api",
  "endpoint",
  "database",
  "query",
  "sql",
  "typescript",
  "javascript",
  "python",
  "rust",
  "go",
  "java",
  "react",
  "component",
  "hook",
  "test",
  "unit test",
  "fix",
  "bug",
  "error",
  "exception",
  "stack trace",
  "optimize",
  "performance",
  "async",
  "promise",
  "type",
  "interface",
  "schema",
  "migration",
  "deploy",
  "docker",
  "regex",
  "parse",
  "compile",
  "build",
  "lint",
];

const QUICK_SIGNALS = [
  "format",
  "convert",
  "transform",
  "translate",
  "summarize",
  "summary",
  "list",
  "count",
  "sort",
  "filter",
  "extract",
  "json",
  "csv",
  "yaml",
  "xml",
  "markdown",
  "rewrite",
  "rephrase",
  "simplify",
  "explain simply",
  "template",
  "boilerplate",
  "placeholder",
  "capitalize",
  "lowercase",
  "uppercase",
  "trim",
  "hello",
  "hi",
  "test",
  "ping",
];

function scoreSignals(task: string, signals: string[]): number {
  const lower = task.toLowerCase();
  return signals.reduce((score, signal) => {
    return score + (lower.includes(signal) ? 1 : 0);
  }, 0);
}

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export function pickModel(task: string): string {
  const codeScore = scoreSignals(task, CODE_SIGNALS);
  const quickScore = scoreSignals(task, QUICK_SIGNALS);

  if (codeScore > quickScore) return SMART_MODEL;
  if (quickScore > codeScore) return FAST_MODEL;

  const tokens = estimateTokens(task);
  if (tokens > 200) return SMART_MODEL;
  return FAST_MODEL;
}

export function getModelForType(type: "smart" | "fast"): string {
  return type === "smart" ? SMART_MODEL : FAST_MODEL;
}

export { SMART_MODEL, FAST_MODEL };
