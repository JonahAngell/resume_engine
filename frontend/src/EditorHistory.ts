export type CommandState = "idle" | "busy" | "error";

export type EditorCommand = {
  id: string;
  label: string;
  compositionId: string;
  sessionId: string;
  preRevision: number;
  identity: Record<string, string | number | boolean | null>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
};

export class EditorHistory {
  private undoStack: EditorCommand[] = [];
  private redoStack: EditorCommand[] = [];
  private state: CommandState = "idle";
  private compositionId = "";
  private sessionId = "";
  private listeners = new Set<() => void>();

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  private notify() {
    for (const listener of this.listeners) listener();
  }
  begin(compositionId: string, sessionId: string) {
    if (this.compositionId !== compositionId || this.sessionId !== sessionId) {
      this.compositionId = compositionId;
      this.sessionId = sessionId;
      this.clear();
    }
  }
  clear() {
    this.undoStack = [];
    this.redoStack = [];
    this.state = "idle";
    this.notify();
  }
  record(command: EditorCommand) {
    if (
      command.compositionId !== this.compositionId ||
      command.sessionId !== this.sessionId
    )
      return;
    if (!command.id || !Object.keys(command.identity).length)
      throw new Error("Undo command requires durable identity.");
    this.undoStack.push(command);
    this.redoStack = [];
    this.notify();
  }
  private async run(
    source: EditorCommand[],
    destination: EditorCommand[],
    direction: "undo" | "redo",
  ) {
    if (this.state === "busy") return;
    const command = source[source.length - 1];
    if (!command) return;
    this.state = "busy";
    this.notify();
    try {
      await command[direction]();
      source.pop();
      destination.push(command);
      this.state = "idle";
    } catch (error) {
      this.state = "error";
      throw error;
    } finally {
      this.notify();
    }
  }
  undo() {
    return this.run(this.undoStack, this.redoStack, "undo");
  }
  redo() {
    return this.run(this.redoStack, this.undoStack, "redo");
  }
  get snapshot() {
    return {
      canUndo: this.undoStack.length > 0 && this.state !== "busy",
      canRedo: this.redoStack.length > 0 && this.state !== "busy",
      busy: this.state === "busy",
      state: this.state,
    };
  }
}
