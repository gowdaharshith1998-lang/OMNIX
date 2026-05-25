import { Experiment, listPublisher, type Mismatch } from "../src/index.js";

describe("Experiment", () => {
  test("returns control on agreement, publishes nothing", async () => {
    const sink: Mismatch[] = [];
    const exp = new Experiment<number, number>("e", listPublisher(sink))
      .use((x) => x + 1)
      .try((x) => x + 1);
    expect(await exp.run(5)).toBe(6);
    expect(sink).toEqual([]);
  });

  test("publishes mismatch but still returns control", async () => {
    const sink: Mismatch[] = [];
    const exp = new Experiment<number, number>("e", listPublisher(sink))
      .use((x) => x + 1)
      .try((x) => x + 2);
    expect(await exp.run(5)).toBe(6);
    expect(sink).toHaveLength(1);
    expect(sink[0].candidate.value).toBe(7);
  });

  test("candidate exception captured", async () => {
    const sink: Mismatch[] = [];
    const exp = new Experiment<number, number>("e", listPublisher(sink))
      .use((x) => x)
      .try(() => {
        throw new Error("boom");
      });
    expect(await exp.run(1)).toBe(1);
    expect(sink[0].candidate.exception).toContain("boom");
  });

  test("enabled=false skips candidate", async () => {
    const sink: Mismatch[] = [];
    const exp = new Experiment<number, number>("e", listPublisher(sink))
      .use(() => 1)
      .try(() => 2)
      .withEnabled(() => false);
    expect(await exp.run(0)).toBe(1);
    expect(sink).toEqual([]);
  });
});
