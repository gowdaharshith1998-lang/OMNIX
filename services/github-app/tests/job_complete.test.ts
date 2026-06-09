import {
  sanitizeReplicationBranchName,
  validateJobCompletePayload,
  validateTargetPath,
} from "../src/handlers/job_complete.js";

describe("job-complete payload validation", () => {
  test("accepts normal repository paths", () => {
    expect(validateTargetPath("src/main/java/Foo.java")).toBe("src/main/java/Foo.java");
  });

  test("rejects path traversal and absolute paths", () => {
    expect(() => validateTargetPath("../.github/workflows/pwn.yml")).toThrow();
    expect(() => validateTargetPath("/tmp/pwn")).toThrow();
    expect(() => validateTargetPath("src\\..\\pwn")).toThrow();
  });

  test("rejects workflow file writes", () => {
    expect(() => validateTargetPath(".github/workflows/omnix.yml")).toThrow();
    expect(() => validateTargetPath(".github//workflows/pwn.yml")).toThrow();
    expect(() => validateTargetPath(".github\\workflows\\pwn.yml")).toThrow();
  });

  test("rejects malformed repository names", () => {
    expect(() =>
      validateJobCompletePayload({
        job_id: "job-1",
        installation_id: 1,
        repo: "owner/repo/extra",
        units: [],
      }),
    ).toThrow();
  });

  test("sanitizes branch suffixes", () => {
    expect(sanitizeReplicationBranchName("job/../../main")).toBe(
      "omnix/replicate/job-------main",
    );
  });
});
