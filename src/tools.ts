import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import * as path from "node:path";
import * as ollama from "./ollama-client.js";
import * as cache from "./cache.js";
import {
  pickModel,
  getModelForType,
  SMART_MODEL,
  FAST_MODEL,
} from "./router.js";
import { agentLock } from "./lock.js";

const execFileAsync = promisify(execFile);
const MFLUX_BIN = path.join(
  process.env.HOME ?? "/Users/shaka-mac-mini",
  "macs-tools/python/bin/mflux-generate",
);
const OUTPUT_DIR = path.join(
  process.env.HOME ?? "/Users/shaka-mac-mini",
  "macs/generated",
);

type ToolResult = {
  content: { type: "text"; text: string }[];
  isError?: boolean;
};

async function withLock(
  name: string,
  fn: () => Promise<ToolResult>,
): Promise<ToolResult> {
  const { running, queued } = agentLock.status();
  const waitMsg = running
    ? `[queue] waiting for ${running} to finish (${queued} in queue)...\n`
    : "";
  await agentLock.acquire(name);
  try {
    const result = await fn();
    if (waitMsg && result.content[0]) {
      result.content[0].text = waitMsg + result.content[0].text;
    }
    return result;
  } finally {
    agentLock.release();
  }
}

export function registerTools(server: McpServer): void {
  server.tool(
    "delegate",
    "Delegate a task to a local LLM. Auto-picks the best model based on task complexity. Use this for any work that doesn't require Claude's judgment. Only one agent runs at a time — others queue automatically.",
    {
      task: z.string().describe("The task or prompt to delegate"),
      agent: z
        .enum(["smart", "fast"])
        .optional()
        .describe(
          "Force a specific agent: 'smart' (Qwen3 8B) or 'fast' (Gemma 3 4B). Omit for auto-routing.",
        ),
      system: z
        .string()
        .optional()
        .describe("Optional system prompt to guide the agent's behavior"),
    },
    async ({ task, agent, system }) => {
      const model = agent ? getModelForType(agent) : pickModel(task);
      return withLock(`delegate:${model}`, async () => {
        const response = await ollama.generate(model, task, system);
        return {
          content: [
            { type: "text" as const, text: `[${model}]\n\n${response}` },
          ],
        };
      });
    },
  );

  server.tool(
    "code_gen",
    "Generate, refactor, or debug code using the smart local model (Qwen3 8B). Best for coding tasks that don't need Claude's reasoning. Queued if another agent is running.",
    {
      prompt: z
        .string()
        .describe("What code to generate or what to do with the code"),
      language: z
        .string()
        .optional()
        .describe("Programming language (e.g., 'python', 'typescript')"),
      context: z
        .string()
        .optional()
        .describe("Existing code context to work with"),
    },
    async ({ prompt, language, context }) => {
      return withLock("code_gen", async () => {
        const systemPrompt = [
          "You are a precise code generator. Output clean, working code.",
          language && `Language: ${language}.`,
          "No unnecessary explanation — code first, brief comments only if essential.",
        ]
          .filter(Boolean)
          .join(" ");

        const fullPrompt = context
          ? `${prompt}\n\nExisting code:\n${context}`
          : prompt;
        const response = await ollama.generate(
          SMART_MODEL,
          fullPrompt,
          systemPrompt,
        );
        return {
          content: [{ type: "text" as const, text: response }],
        };
      });
    },
  );

  server.tool(
    "quick",
    "Run a quick, simple task using the fast local model (Gemma 3 4B). Best for formatting, converting, simple Q&A. Queued if another agent is running.",
    {
      prompt: z.string().describe("The simple task to perform"),
    },
    async ({ prompt }) => {
      return withLock("quick", async () => {
        const response = await ollama.generate(
          FAST_MODEL,
          prompt,
          "Be concise and direct.",
        );
        return {
          content: [{ type: "text" as const, text: response }],
        };
      });
    },
  );

  server.tool(
    "summarize",
    "Summarize text using the fast local model. Good for logs, docs, long outputs. Queued if another agent is running.",
    {
      text: z.string().describe("The text to summarize"),
      style: z
        .enum(["brief", "bullets", "detailed"])
        .optional()
        .describe(
          "Summary style: 'brief' (1-2 sentences), 'bullets' (key points), 'detailed' (paragraph)",
        ),
    },
    async ({ text, style = "bullets" }) => {
      return withLock("summarize", async () => {
        const styleGuide: Record<string, string> = {
          brief: "Summarize in 1-2 sentences.",
          bullets:
            "Summarize as bullet points. Each bullet should be one key point.",
          detailed: "Write a detailed summary paragraph.",
        };

        const response = await ollama.generate(
          FAST_MODEL,
          `Summarize the following:\n\n${text}`,
          styleGuide[style],
        );
        return {
          content: [{ type: "text" as const, text: response }],
        };
      });
    },
  );

  server.tool(
    "transform",
    "Transform or convert data/text using the fast local model. Good for format conversion, parsing, restructuring. Queued if another agent is running.",
    {
      input: z.string().describe("The data or text to transform"),
      instruction: z
        .string()
        .describe(
          "How to transform it (e.g., 'convert to JSON', 'make a markdown table', 'extract emails')",
        ),
    },
    async ({ input, instruction }) => {
      return withLock("transform", async () => {
        const response = await ollama.generate(
          FAST_MODEL,
          `${instruction}\n\nInput:\n${input}`,
          "Transform the input exactly as instructed. Output only the result.",
        );
        return {
          content: [{ type: "text" as const, text: response }],
        };
      });
    },
  );

  server.tool(
    "agents",
    "List available local models, check Ollama health, and show current queue status.",
    {},
    async () => {
      const healthy = await ollama.isHealthy();
      if (!healthy) {
        return {
          content: [
            {
              type: "text" as const,
              text: "Ollama is not running. Start it with: open -a Ollama",
            },
          ],
        };
      }

      const models = await ollama.listModels();
      const lines = models.map((m) => {
        const sizeGB = (m.size / 1e9).toFixed(1);
        const role = m.name.startsWith("qwen")
          ? "smart (coding/reasoning)"
          : m.name.startsWith("gemma")
            ? "fast (quick tasks)"
            : "general";
        return `- ${m.name} [${sizeGB}GB] — ${role}`;
      });

      const { running, queued } = agentLock.status();
      const lockLine = running
        ? `\nAgent lock: ${running} running, ${queued} queued`
        : "\nAgent lock: idle";

      const cacheStats = cache.stats();
      const cacheLine = `\nCache: ${cacheStats.entries}/${cacheStats.maxSize} entries, ${cacheStats.ttlMinutes}min TTL`;

      return {
        content: [
          {
            type: "text" as const,
            text: `Ollama: healthy\nModels:\n${lines.join("\n") || "(no models installed)"}${lockLine}${cacheLine}`,
          },
        ],
      };
    },
  );

  server.tool(
    "chain",
    "Run multiple steps sequentially, passing each output to the next. Each step runs through the lock system. Good for: research → summarize → format pipelines.",
    {
      steps: z
        .array(
          z.object({
            agent: z
              .enum(["smart", "fast"])
              .optional()
              .describe("Which agent to use (default: auto)"),
            prompt: z
              .string()
              .describe(
                "The prompt for this step. Use {{prev}} to reference the previous step's output.",
              ),
            system: z
              .string()
              .optional()
              .describe("Optional system prompt for this step"),
          }),
        )
        .min(2)
        .describe("List of steps to execute in order"),
    },
    async ({ steps }) => {
      let prevOutput = "";
      const results: string[] = [];

      for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        const prompt = step.prompt.replace(/\{\{prev\}\}/g, prevOutput);
        const model = step.agent
          ? getModelForType(step.agent)
          : pickModel(prompt);

        const result = await withLock(
          `chain:step${i + 1}:${model}`,
          async () => {
            const response = await ollama.generate(model, prompt, step.system);
            return {
              content: [{ type: "text" as const, text: response }],
            };
          },
        );

        prevOutput = result.content[0].text;
        results.push(`--- Step ${i + 1} [${model}] ---\n${prevOutput}`);
      }

      return {
        content: [{ type: "text" as const, text: results.join("\n\n") }],
      };
    },
  );

  server.tool(
    "image_gen",
    "Generate an image using FLUX.1 Schnell locally on Apple Silicon. Uses the agent lock — only runs when no other agent is active. Output saved to ~/macs/generated/.",
    {
      prompt: z.string().describe("Text description of the image to generate"),
      width: z
        .number()
        .optional()
        .describe("Image width (default 512, multiple of 16)"),
      height: z
        .number()
        .optional()
        .describe("Image height (default 512, multiple of 16)"),
      steps: z
        .number()
        .optional()
        .describe("Inference steps (default 4, more = better but slower)"),
      seed: z.number().optional().describe("Random seed for reproducibility"),
      filename: z
        .string()
        .optional()
        .describe("Output filename without extension"),
    },
    async ({
      prompt,
      width = 512,
      height = 512,
      steps = 4,
      seed,
      filename,
    }) => {
      return withLock("image_gen:flux", async () => {
        const { mkdirSync } = await import("node:fs");
        mkdirSync(OUTPUT_DIR, { recursive: true });

        const slug =
          filename ??
          prompt
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .slice(0, 40) +
            "-" +
            Date.now();
        const outputPath = path.join(OUTPUT_DIR, `${slug}.png`);

        const args = [
          "--model",
          "madroid/flux.1-schnell-mflux-4bit",
          "--base-model",
          "schnell",
          "--low-ram",
          "--prompt",
          prompt,
          "--width",
          String(width),
          "--height",
          String(height),
          "--steps",
          String(steps),
          "--output",
          outputPath,
        ];
        if (seed !== undefined) args.push("--seed", String(seed));

        try {
          const { stderr } = await execFileAsync(MFLUX_BIN, args, {
            timeout: 300_000,
          });
          return {
            content: [
              {
                type: "text" as const,
                text: `Image generated: ${outputPath}\nPrompt: "${prompt}"\nSize: ${width}x${height}, Steps: ${steps}${seed !== undefined ? `, Seed: ${seed}` : ""}\n\n${stderr ?? ""}`.trim(),
              },
            ],
          };
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          return {
            content: [
              { type: "text" as const, text: `image_gen error: ${msg}` },
            ],
            isError: true,
          };
        }
      });
    },
  );
}
