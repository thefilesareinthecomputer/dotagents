export interface ConsoleLine {
  at: number;
  level: "info" | "warn" | "error";
  text: string;
}

const CAPACITY = 200;

export class ConsoleBuffer {
  private lines: ConsoleLine[] = [];

  push(level: ConsoleLine["level"], text: string): void {
    this.lines.push({ at: Date.now(), level, text });
    if (this.lines.length > CAPACITY) {
      this.lines.splice(0, this.lines.length - CAPACITY);
    }
  }

  recent(count: number): ConsoleLine[] {
    return this.lines.slice(-count);
  }

  errors(): ConsoleLine[] {
    return this.lines.filter((line) => line.level === "error");
  }

  clear(): void {
    this.lines = [];
  }
}

export const sharedConsole = new ConsoleBuffer();

export function logInfo(text: string): void {
  sharedConsole.push("info", text);
}

export function logError(text: string): void {
  sharedConsole.push("error", text);
}
