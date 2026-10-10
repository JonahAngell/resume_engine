export type SaveState = "Unsaved" | "Saving" | "Saved" | "Error" | "Conflict";
export class SaveCoordinator<T> {
  private localVersion = 0;
  private confirmedVersion = 0;
  private chain: Promise<void> = Promise.resolve();
  private timer: number | undefined;
  constructor(
    private commit: (value: T, version: number) => Promise<void>,
    private state: (s: SaveState) => void,
  ) {}
  dirty() {
    this.localVersion += 1;
    this.state("Unsaved");
    return this.localVersion;
  }
  schedule(value: T, delay = 700) {
    const version = this.dirty();
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => this.enqueue(value, version), delay);
  }
  flush(value: T) {
    window.clearTimeout(this.timer);
    const version = this.localVersion || this.dirty();
    return this.enqueue(value, version);
  }
  private enqueue(value: T, version: number) {
    this.chain = this.chain.then(async () => {
      this.state("Saving");
      try {
        await this.commit(value, version);
        this.confirmedVersion = Math.max(this.confirmedVersion, version);
        this.state(
          this.confirmedVersion === this.localVersion ? "Saved" : "Unsaved",
        );
      } catch (e: any) {
        this.state(e?.status === 409 ? "Conflict" : "Error");
        throw e;
      }
    });
    return this.chain;
  }
  get unsynchronized() {
    return this.confirmedVersion !== this.localVersion;
  }
}
