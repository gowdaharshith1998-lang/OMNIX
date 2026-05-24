export type RunState = "idle" | "running" | "decision" | "done";

export type GraphSide = "source" | "target";

export type LanguageOption = {
  id: string;
  label: string;
  hint: string;
};

export const TARGET_LANGUAGES: LanguageOption[] = [
  { id: "java21", label: "Java 21", hint: "Spring Boot 4" },
  { id: "python314", label: "Python 3.14", hint: "FastAPI" },
  { id: "go123", label: "Go 1.23", hint: "stdlib" },
  { id: "csharp9", label: "C# .NET 9", hint: "ASP.NET Core" },
  { id: "rust", label: "Rust", hint: "axum" },
  { id: "kotlin", label: "Kotlin", hint: "Spring" },
  { id: "ts22", label: "TypeScript", hint: "Node 22" },
  { id: "cpp23", label: "Modern C++", hint: "C++23" },
];

export const SOURCE_LANGUAGES: LanguageOption[] = [
  { id: "auto", label: "Auto-detect", hint: "from index" },
  { id: "cobol", label: "COBOL-85", hint: "legacy mainframe" },
  { id: "java8", label: "Java 8", hint: "legacy enterprise" },
  { id: "python27", label: "Python 2.7", hint: "legacy" },
  { id: "vb6", label: "VB6", hint: "legacy Windows" },
  { id: "perl5", label: "Perl 5", hint: "scripts" },
];

export type ChatRole = "user" | "agent" | "system";

export type ChatAction = {
  id: string;
  label: string;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  ts: number;
  text: string;
  actions?: ChatAction[];
};

export type DecisionOption = {
  id: string;
  title: string;
  hint?: string;
  recommended?: boolean;
};

export type DecisionPayload = {
  gate: string;
  symbol: string;
  question: string;
  options: DecisionOption[];
};

export type RightTabId = "xray" | "chat" | "receipts" | "history";

export const RIGHT_TAB_ORDER: { id: RightTabId; label: string }[] = [
  { id: "xray", label: "X-RAY" },
  { id: "chat", label: "CHAT" },
  { id: "receipts", label: "RECEIPTS" },
  { id: "history", label: "HISTORY" },
];
