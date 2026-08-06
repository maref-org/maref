/**
 * @maref-org/mcp-governance — In-memory decision cache
 *
 * Mirrors the caching logic from the OpenClaw maref-governance plugin.
 * Allow decisions cached for cacheTtlMs, block for cacheBlockTtlMs.
 * HITL decisions are never cached.
 */

import type { CachedDecision } from "./types.js";

export interface CacheConfig {
  cacheTtlMs: number;
  cacheBlockTtlMs: number;
}

export interface CacheStats {
  size: number;
  hits: number;
  misses: number;
}

export class DecisionCache {
  private store = new Map<string, CachedDecision>();
  private hits = 0;
  private misses = 0;
  private config: CacheConfig;

  constructor(config: CacheConfig) {
    this.config = config;
  }

  /** Build a cache key from operation prefix + identifier */
  static key(operation: string, identifier: string): string {
    return `${operation}:${identifier}`;
  }

  /** Get cached decision, or null on miss/expiry */
  get(key: string): CachedDecision | null {
    const entry = this.store.get(key);
    if (!entry) {
      this.misses++;
      return null;
    }
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      this.misses++;
      return null;
    }
    this.hits++;
    return entry;
  }

  /** Store a decision in cache. Skips HITL and zero-TTL configs. */
  set(
    key: string,
    verdict: "allow" | "block",
    rule_id: string,
    reason: string,
    risk_score: number,
  ): void {
    const ttl =
      verdict === "block" ? this.config.cacheBlockTtlMs : this.config.cacheTtlMs;
    if (ttl <= 0) return;
    this.store.set(key, {
      verdict,
      rule_id,
      reason,
      risk_score,
      expiresAt: Date.now() + ttl,
    });
  }

  /** Get cache statistics */
  stats(): CacheStats {
    return {
      size: this.store.size,
      hits: this.hits,
      misses: this.misses,
    };
  }
}
