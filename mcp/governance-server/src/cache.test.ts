import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionCache } from "./cache.js";

describe("DecisionCache", () => {
  let cache: DecisionCache;

  beforeEach(() => {
    vi.useFakeTimers();
    cache = new DecisionCache({ cacheTtlMs: 60_000, cacheBlockTtlMs: 120_000 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null on cache miss", () => {
    expect(cache.get("write:/tmp/test.txt")).toBeNull();
  });

  it("returns cached allow decision", () => {
    cache.set("write:/tmp/test.txt", "allow", "ALLOW-RULE", "allowed", 0.1);
    const entry = cache.get("write:/tmp/test.txt");
    expect(entry).not.toBeNull();
    expect(entry!.verdict).toBe("allow");
    expect(entry!.rule_id).toBe("ALLOW-RULE");
  });

  it("returns cached block decision", () => {
    cache.set("write:/tmp/secret.txt", "block", "BLOCK-RULE", "blocked", 0.9);
    const entry = cache.get("write:/tmp/secret.txt");
    expect(entry).not.toBeNull();
    expect(entry!.verdict).toBe("block");
  });

  it("expires after TTL for allow", () => {
    cache.set("write:/tmp/test.txt", "allow", "RULE-1", "ok", 0.1);
    vi.advanceTimersByTime(60_001);
    expect(cache.get("write:/tmp/test.txt")).toBeNull();
  });

  it("expires after block TTL", () => {
    cache.set("write:/tmp/secret.txt", "block", "RULE-2", "blocked", 0.9);
    vi.advanceTimersByTime(60_000); // Within block TTL of 120s
    expect(cache.get("write:/tmp/secret.txt")).not.toBeNull();
    vi.advanceTimersByTime(60_001); // Past block TTL
    expect(cache.get("write:/tmp/secret.txt")).toBeNull();
  });

  it("does not cache when TTL is 0", () => {
    cache = new DecisionCache({ cacheTtlMs: 0, cacheBlockTtlMs: 0 });
    cache.set("write:/tmp/test.txt", "allow", "RULE-1", "ok", 0.1);
    expect(cache.get("write:/tmp/test.txt")).toBeNull();
  });

  it("tracks stats correctly", () => {
    expect(cache.stats()).toEqual({ size: 0, hits: 0, misses: 0 });

    cache.get("key1"); // miss
    expect(cache.stats().misses).toBe(1);

    cache.set("key2", "allow", "R", "ok", 0.1);
    cache.get("key2"); // hit
    expect(cache.stats().hits).toBe(1);
    expect(cache.stats().size).toBe(1);

    cache.get("key3"); // miss
    expect(cache.stats().misses).toBe(2);
  });

  it("builds correct cache keys", () => {
    expect(DecisionCache.key("write", "/tmp/test.txt")).toBe("write:/tmp/test.txt");
    expect(DecisionCache.key("execute", "ls -la")).toBe("execute:ls -la");
  });
});
