export interface WebVitalMetric {
  name: string;
  value: number;
  rating: "good" | "needs-improvement" | "poor";
}

type VitalReportCallback = (metric: WebVitalMetric) => void;

let onVitalReport: VitalReportCallback | null = null;

export function setVitalReportHandler(cb: VitalReportCallback) {
  onVitalReport = cb;
}

function getRating(name: string, value: number): "good" | "needs-improvement" | "poor" {
  const thresholds: Record<string, { good: number; poor: number }> = {
    LCP: { good: 2500, poor: 4000 },
    INP: { good: 200, poor: 500 },
    CLS: { good: 0.1, poor: 0.25 },
    FCP: { good: 1800, poor: 3000 },
    TTFB: { good: 800, poor: 1800 },
  };
  const t = thresholds[name];
  if (!t) return "needs-improvement";
  if (value <= t.good) return "good";
  if (value <= t.poor) return "needs-improvement";
  return "poor";
}

async function getWebVitals() {
  try {
    const { onCLS, onFCP, onLCP, onTTFB } = await import("web-vitals");
    const report = (name: string) => (metric: { value: number }) => {
      const value = metric.value;
      onVitalReport?.({ name, value, rating: getRating(name, value) });
    };
    onCLS(report("CLS"));
    onFCP(report("FCP"));
    onLCP(report("LCP"));
    onTTFB(report("TTFB"));
  } catch {
    // web-vitals not available
  }
}

export function initWebVitals() {
  if (typeof window !== "undefined") {
    getWebVitals();
  }
}
