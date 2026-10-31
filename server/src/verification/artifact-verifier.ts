import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { delimiter, resolve } from "node:path";
import type { ArtifactVerifierConfig } from "../config/env.js";
import type {
  ArtifactContractErrorResponse,
  ArtifactVerificationRequest,
  ArtifactVerificationResponse,
  VerifiedArtifactResponse,
} from "./contracts.js";
import { ArtifactVerificationError } from "./errors.js";
import { ArtifactContractValidator } from "./schema-validator.js";

const PYTHON_MODULE = "tradepilot.contracts";

class Semaphore {
  private active = 0;
  private readonly waiting: Array<() => void> = [];

  public constructor(
    private readonly maximum: number,
    private readonly maximumWaiting: number,
  ) {}

  public async acquire(): Promise<() => void> {
    if (this.active >= this.maximum) {
      if (this.waiting.length >= this.maximumWaiting) {
        throw new ArtifactVerificationError(
          "CAPACITY", "VERIFIER_OVERLOADED", "artifact verifier is at capacity", true,
        );
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

interface ProcessResult {
  readonly exitCode: number | null;
  readonly stdout: Buffer;
}

function childEnvironment(pythonPath: string): NodeJS.ProcessEnv {
  const allowed = [
    "PATH", "Path", "PATHEXT", "SYSTEMROOT", "SystemRoot", "WINDIR",
    "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL",
  ] as const;
  const environment: NodeJS.ProcessEnv = {
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
    PYTHONPATH: pythonPath,
  };
  for (const name of allowed) {
    const value = process.env[name];
    if (value !== undefined) environment[name] = value;
  }
  return environment;
}

export class ArtifactVerifierService {
  private readonly validator: ArtifactContractValidator;
  private readonly semaphore: Semaphore;

  public constructor(private readonly config: ArtifactVerifierConfig) {
    this.validator = new ArtifactContractValidator(config.schemaDirectory);
    this.semaphore = new Semaphore(config.maxConcurrency, config.maxPendingRequests);
  }

  public async verify(request: ArtifactVerificationRequest): Promise<VerifiedArtifactResponse> {
    this.validator.assertRequest(request);
    const input = Buffer.from(`${JSON.stringify(request)}\n`, "utf8");
    if (input.byteLength > this.config.maxInputBytes) {
      throw new ArtifactVerificationError(
        "INVALID_REQUEST", "REQUEST_TOO_LARGE", "artifact verification request is too large", false,
      );
    }

    const release = await this.semaphore.acquire();
    try {
      const result = await this.invoke(input);
      let response: ArtifactVerificationResponse;
      try {
        response = this.parseResponse(result.stdout);
      } catch (error) {
        if (result.exitCode !== 0) {
          throw new ArtifactVerificationError(
            "SUBPROCESS_FAILURE", "VERIFIER_EXIT_FAILURE", "artifact verifier failed", true,
          );
        }
        throw error;
      }
      if (response.request_id !== request.request_id) {
        throw new ArtifactVerificationError(
          "PROTOCOL_FAILURE", "REQUEST_ID_MISMATCH", "artifact verifier response mismatch", false,
        );
      }
      if (response.status === "ERROR") {
        throw this.contractError(response);
      }
      if (result.exitCode !== 0) {
        throw new ArtifactVerificationError(
          "SUBPROCESS_FAILURE", "VERIFIER_EXIT_FAILURE", "artifact verifier failed", true,
        );
      }
      return response;
    } finally {
      release();
    }
  }

  private invoke(input: Buffer): Promise<ProcessResult> {
    return new Promise((resolveProcess, rejectProcess) => {
      const child = spawn(
        this.config.pythonExecutable,
        [
          "-m", PYTHON_MODULE,
          "--dataset-root", this.config.datasetRoot,
          "--report-root", this.config.reportRoot,
        ],
        {
          cwd: this.config.pythonWorkingDirectory,
          shell: false,
          windowsHide: true,
          detached: process.platform !== "win32",
          env: childEnvironment(
            [
              resolve(this.config.pythonWorkingDirectory, "src"),
              process.env["PYTHONPATH"],
            ].filter((value): value is string => value !== undefined && value !== "").join(delimiter),
          ),
          stdio: ["pipe", "pipe", "pipe"],
        },
      );
      let settled = false;
      const stdout: Buffer[] = [];
      const stderr: Buffer[] = [];
      let stdoutBytes = 0;
      let stderrBytes = 0;

      const fail = (error: ArtifactVerificationError): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.terminateTree(child);
        rejectProcess(error);
      };
      const timer = setTimeout(() => fail(new ArtifactVerificationError(
        "TIMEOUT", "VERIFIER_TIMEOUT", "artifact verifier timed out", true,
      )), this.config.timeoutMs);

      child.once("error", () => fail(new ArtifactVerificationError(
        "SUBPROCESS_FAILURE", "VERIFIER_START_FAILED", "artifact verifier could not start", true,
      )));
      child.stdout.on("data", (chunk: Buffer) => {
        stdoutBytes += chunk.byteLength;
        if (stdoutBytes > this.config.maxOutputBytes) {
          fail(new ArtifactVerificationError(
            "PROTOCOL_FAILURE", "STDOUT_LIMIT_EXCEEDED", "artifact verifier output exceeded its limit", false,
          ));
          return;
        }
        stdout.push(chunk);
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderrBytes += chunk.byteLength;
        if (stderrBytes > this.config.maxErrorBytes) {
          fail(new ArtifactVerificationError(
            "PROTOCOL_FAILURE", "STDERR_LIMIT_EXCEEDED", "artifact verifier diagnostics exceeded their limit", false,
          ));
          return;
        }
        stderr.push(chunk);
      });
      child.once("close", (exitCode) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolveProcess({ exitCode, stdout: Buffer.concat(stdout) });
      });
      child.stdin.once("error", () => fail(new ArtifactVerificationError(
        "SUBPROCESS_FAILURE", "STDIN_FAILURE", "artifact verifier input failed", true,
      )));
      child.stdin.end(input);
    });
  }

  private terminateTree(child: ChildProcessWithoutNullStreams): void {
    if (child.pid === undefined) return;
    if (process.platform === "win32") {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        shell: false,
        windowsHide: true,
        stdio: "ignore",
      });
      killer.unref();
      return;
    }
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
  }

  private parseResponse(output: Buffer): ArtifactVerificationResponse {
    const text = output.toString("utf8");
    const lines = text.split(/\r?\n/u).filter((line) => line.length > 0);
    if (lines.length !== 1 || lines[0] === undefined) {
      throw new ArtifactVerificationError(
        "PROTOCOL_FAILURE", "INVALID_STDOUT", "artifact verifier returned invalid output", false,
      );
    }
    let value: unknown;
    try {
      value = JSON.parse(lines[0]);
    } catch {
      throw new ArtifactVerificationError(
        "PROTOCOL_FAILURE", "INVALID_JSON_RESPONSE", "artifact verifier returned invalid JSON", false,
      );
    }
    this.validator.assertResponse(value);
    return value;
  }

  private contractError(response: ArtifactContractErrorResponse): ArtifactVerificationError {
    return new ArtifactVerificationError(
      "CONTRACT_FAILURE",
      response.error.code,
      "artifact verification failed",
      response.error.retryable,
    );
  }
}
