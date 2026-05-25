import { QuotaTracker } from "../src/quota.js";

describe("QuotaTracker", () => {
  test("free tier permits first run", () => {
    const q = new QuotaTracker();
    expect(q.check(123, "free").allowed).toBe(true);
  });

  test("free tier blocks after limit", () => {
    const q = new QuotaTracker();
    for (let i = 0; i < 5; i++) q.record(123);
    const c = q.check(123, "free");
    expect(c.allowed).toBe(false);
    expect(c.reason).toContain("free tier limit reached");
  });

  test("team tier is unlimited", () => {
    const q = new QuotaTracker();
    for (let i = 0; i < 100; i++) q.record(123);
    expect(q.check(123, "team").allowed).toBe(true);
  });

  test("reset clears usage", () => {
    const q = new QuotaTracker();
    for (let i = 0; i < 10; i++) q.record(123);
    q.reset(123);
    expect(q.check(123, "free").allowed).toBe(true);
  });
});
