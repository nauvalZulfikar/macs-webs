import * as cache from "./cache.js";

const OLLAMA_BASE = "http://localhost:11434";
const TIMEOUT = 120_000;
const MAX_RETRIES = 2;

export interface OllamaResponse {
  model: string;
  response: string;
  done: boolean;
  total_duration?: number;
  eval_count?: number;
}

export interface OllamaModel {
  name: string;
  size: number;
  digest: string;
  modified_at: string;
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retries = MAX_RETRIES,
): Promise<Response> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), TIMEOUT);
      const res = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timer);
      if (res.ok) return res;
      if (attempt < retries && res.status >= 500) continue;
      const text = await res.text();
      throw new Error(`Ollama error ${res.status}: ${text}`);
    } catch (err: unknown) {
      if (attempt >= retries) throw err;
      if (err instanceof Error && err.name === "AbortError") {
        throw new Error(`Ollama timeout after ${TIMEOUT / 1000}s`);
      }
    }
  }
  throw new Error("Ollama: max retries exceeded");
}

export async function generate(
  model: string,
  prompt: string,
  system?: string,
): Promise<string> {
  const cached = cache.get(model, prompt, system);
  if (cached) return `[cached] ${cached}`;

  const body: Record<string, unknown> = {
    model,
    prompt,
    stream: false,
    think: false,
  };
  if (system) body.system = system;

  const res = await fetchWithRetry(`${OLLAMA_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = (await res.json()) as OllamaResponse;
  cache.set(model, prompt, data.response, system);
  return data.response;
}

export async function chat(
  model: string,
  messages: { role: string; content: string }[],
  system?: string,
): Promise<string> {
  const body: Record<string, unknown> = {
    model,
    messages: system
      ? [{ role: "system", content: system }, ...messages]
      : messages,
    stream: false,
    think: false,
  };

  const res = await fetchWithRetry(`${OLLAMA_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = (await res.json()) as { message: { content: string } };
  return data.message.content;
}

export async function listModels(): Promise<OllamaModel[]> {
  const res = await fetch(`${OLLAMA_BASE}/api/tags`);
  if (!res.ok) {
    throw new Error(`Ollama error ${res.status}: ${await res.text()}`);
  }
  const data = (await res.json()) as { models: OllamaModel[] };
  return data.models;
}

export async function isHealthy(): Promise<boolean> {
  try {
    const res = await fetch(OLLAMA_BASE);
    return res.ok;
  } catch {
    return false;
  }
}
