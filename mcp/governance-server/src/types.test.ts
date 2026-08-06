import { describe, it, expect } from "vitest";
import {
  WRITE_TOOL_NAMES,
  EXECUTE_TOOL_NAMES,
} from "./types.js";

describe("WRITE_TOOL_NAMES", () => {
  it("contains standard write tool names", () => {
    expect(WRITE_TOOL_NAMES.has("write")).toBe(true);
    expect(WRITE_TOOL_NAMES.has("write_file")).toBe(true);
    expect(WRITE_TOOL_NAMES.has("overwrite_file")).toBe(true);
    expect(WRITE_TOOL_NAMES.has("apply_patch")).toBe(true);
  });
});

describe("EXECUTE_TOOL_NAMES", () => {
  it("contains standard execute tool names", () => {
    expect(EXECUTE_TOOL_NAMES.has("execute")).toBe(true);
    expect(EXECUTE_TOOL_NAMES.has("bash")).toBe(true);
    expect(EXECUTE_TOOL_NAMES.has("run_command")).toBe(true);
  });
});
