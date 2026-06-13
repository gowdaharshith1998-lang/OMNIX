import {
  _SLASH_REGEX_FOR_TESTS as SLASH,
  isTrustedSlashCommandAuthor,
} from "../src/handlers/pr_comment.js";

describe("/omnix replicate slash command", () => {
  test("matches bare command", () => {
    expect(SLASH.exec("/omnix replicate")?.[2]).toBeUndefined();
  });

  test("matches with scope", () => {
    expect(SLASH.exec("/omnix replicate src/foo")?.[2]).toBe("src/foo");
  });

  test("does not match other commands", () => {
    expect(SLASH.exec("/omnix help")).toBeNull();
    expect(SLASH.exec("/notomnix replicate")).toBeNull();
  });

  test("tolerates trailing whitespace", () => {
    expect(SLASH.exec("/omnix replicate src/x   ")?.[2]).toBe("src/x");
  });
});

describe("slash command author authorization", () => {
  test("allows trusted repository actors", () => {
    expect(isTrustedSlashCommandAuthor("OWNER")).toBe(true);
    expect(isTrustedSlashCommandAuthor("MEMBER")).toBe(true);
    expect(isTrustedSlashCommandAuthor("COLLABORATOR")).toBe(true);
  });

  test("rejects untrusted commenters", () => {
    expect(isTrustedSlashCommandAuthor("CONTRIBUTOR")).toBe(false);
    expect(isTrustedSlashCommandAuthor("NONE")).toBe(false);
    expect(isTrustedSlashCommandAuthor(undefined)).toBe(false);
  });
});
