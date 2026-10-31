import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { delimiter, resolve } from "node:path";
import type { ArtifactVerifierConfig } from "../config/env.js";
import { ArtifactVerificationError } from "./errors.js";

class Semaphore {
  private active = 0;
  private readonly waiting: Array<() => void> = [];
  public constructor(private readonly maximum: number, private readonly maximumWaiting: number) {}
  public async acquire(): Promise<() => void> {
    if (this.active >= this.maximum) {
      if (this.waiting.length >= this.maximumWaiting) {
        throw new ArtifactVerificationError("CAPACITY", "VERIFIER_OVERLOADED", "Python contract runner is at capacity", true);
      }
      await new Promise<void>((resolveWait) => this.waiting.push(resolveWait));
    }
    this.active += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.active -= 1;
      this.waiting.shift()?.();
    };
  }
}

export interface ControlledProcessResult { readonly exitCode: number | null; readonly stdout: Buffer; }

function childEnvironment(pythonPath: string): NodeJS.ProcessEnv {
  const allowed = ["PATH", "Path", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL"] as const;
  const environment: NodeJS.ProcessEnv = { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1", PYTHONPATH: pythonPath };
  for (const name of allowed) {
    const value = process.env[name];
    if (value !== undefined) environment[name] = value;
  }
  return environment;
}

export class ControlledPythonRunner {
  private readonly semaphore: Semaphore;
  public constructor(
    private readonly config: ArtifactVerifierConfig,
    private readonly moduleName: string,
    private readonly fixedArguments: readonly string[],
  ) {
    this.semaphore = new Semaphore(config.maxConcurrency, config.maxPendingRequests);
  }
  public async run(input: Buffer): Promise<ControlledProcessResult> {
    const release = await this.semaphore.acquire();
    try { return await this.invoke(input); } finally { release(); }
  }
  private invoke(input: Buffer): Promise<ControlledProcessResult> {
    return new Promise((resolveProcess, rejectProcess) => {
      const child = spawn(this.config.pythonExecutable, ["-m", this.moduleName, ...this.fixedArguments], {
        cwd: this.config.pythonWorkingDirectory, shell: false, windowsHide: true,
        detached: process.platform !== "win32",
        env: childEnvironment([resolve(this.config.pythonWorkingDirectory, "src"), process.env["PYTHONPATH"]]
          .filter((value): value is string => value !== undefined && value !== "").join(delimiter)),
        stdio: ["pipe", "pipe", "pipe"],
      });
      let settled = false;
      const stdout: Buffer[] = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;
      const fail = (error: ArtifactVerificationError): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.terminateTree(child);
        rejectProcess(error);
      };
      const timer = setTimeout(() => fail(new ArtifactVerificationError("TIMEOUT", "VERIFIER_TIMEOUT", "Python contract timed out", true)), this.config.timeoutMs);
      child.once("error", () => fail(new ArtifactVerificationError("SUBPROCESS_FAILURE", "VERIFIER_START_FAILED", "Python contract could not start", true)));
      child.stdout.on("data", (chunk: Buffer) => {
        stdoutBytes += chunk.byteLength;
        if (stdoutBytes > this.config.maxOutputBytes) {
          fail(new ArtifactVerificationError("PROTOCOL_FAILURE", "STDOUT_LIMIT_EXCEEDED", "Python contract output exceeded its limit", false));
          return;
        }
        stdout.push(chunk);
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderrBytes += chunk.byteLength;
        if (stderrBytes > this.config.maxErrorBytes) {
          fail(new ArtifactVerificationError("PROTOCOL_FAILURE", "STDERR_LIMIT_EXCEEDED", "Python contract diagnostics exceeded their limit", false));
        }
      });
      child.once("close", (exitCode) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolveProcess({ exitCode, stdout: Buffer.concat(stdout) });
      });
      child.stdin.once("error", () => fail(new ArtifactVerificationError("SUBPROCESS_FAILURE", "STDIN_FAILURE", "Python contract input failed", true)));
      child.stdin.end(input);
    });
  }
  private terminateTree(child: ChildProcessWithoutNullStreams): void {
    if (child.pid === undefined) return;
    if (process.platform === "win32") {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { shell: false, windowsHide: true, stdio: "ignore" });
      killer.unref();
      return;
    }
    try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); }
  }
}
