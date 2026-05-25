export type ResultPublisher = (mismatch: Mismatch) => void;

export interface Branch<T> {
  name: "control" | "candidate";
  value: T | null;
  durationMs: number;
  exception?: string;
}

export interface Mismatch {
  experiment: string;
  control: Branch<unknown>;
  candidate: Branch<unknown>;
  context: Record<string, unknown>;
}

export class Experiment<I, O> {
  private control: ((input: I) => O | Promise<O>) | null = null;
  private candidate: ((input: I) => O | Promise<O>) | null = null;
  private comparator: (a: O, b: O) => boolean = (a, b) =>
    JSON.stringify(a) === JSON.stringify(b);
  private enabled: () => boolean = () => true;

  constructor(
    public readonly name: string,
    private readonly publisher?: ResultPublisher,
  ) {}

  use(fn: (input: I) => O | Promise<O>): this {
    this.control = fn;
    return this;
  }

  try(fn: (input: I) => O | Promise<O>): this {
    this.candidate = fn;
    return this;
  }

  withComparator(fn: (a: O, b: O) => boolean): this {
    this.comparator = fn;
    return this;
  }

  withEnabled(fn: () => boolean): this {
    this.enabled = fn;
    return this;
  }

  async run(input: I): Promise<O> {
    if (!this.control) throw new Error(`experiment ${this.name}: no control`);
    const t0 = Date.now();
    const controlValue = await this.control(input);
    const controlMs = Date.now() - t0;
    if (!this.candidate || !this.enabled()) return controlValue;

    const t1 = Date.now();
    let candidateValue: O | null = null;
    let candidateException: string | undefined;
    try {
      candidateValue = await this.candidate(input);
    } catch (e) {
      candidateException = (e as Error).message;
    }
    const candidateMs = Date.now() - t1;

    const agree =
      candidateException === undefined &&
      candidateValue !== null &&
      this.comparator(controlValue, candidateValue);

    if (!agree && this.publisher) {
      this.publisher({
        experiment: this.name,
        control: { name: "control", value: controlValue, durationMs: controlMs },
        candidate: {
          name: "candidate",
          value: candidateValue,
          durationMs: candidateMs,
          exception: candidateException,
        },
        context: { input: JSON.stringify(input) },
      });
    }
    return controlValue;
  }
}

export const listPublisher = (sink: Mismatch[]): ResultPublisher =>
  (m) => sink.push(m);

export const httpPublisher = (baseUrl: string, token?: string): ResultPublisher =>
  (m) => {
    fetch(`${baseUrl}/v1/scientist/mismatches`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(m),
    }).catch(() => {
      /* swallow */
    });
  };
