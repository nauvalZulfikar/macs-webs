export class AgentLock {
  private running: string | null = null;
  private queue: (() => void)[] = [];

  async acquire(agentName: string): Promise<void> {
    if (!this.running) {
      this.running = agentName;
      return;
    }
    return new Promise((resolve) => {
      this.queue.push(() => {
        this.running = agentName;
        resolve();
      });
    });
  }

  release(): void {
    const next = this.queue.shift();
    if (next) {
      next();
    } else {
      this.running = null;
    }
  }

  status(): { running: string | null; queued: number } {
    return { running: this.running, queued: this.queue.length };
  }
}

export const agentLock = new AgentLock();
