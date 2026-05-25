import { _SLASH_REGEX_FOR_TESTS as SLASH } from "../src/handlers/pr_comment.js";

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
