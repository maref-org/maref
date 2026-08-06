export interface ConvergencePoint {
  round: number;
  fnr: number;
  fpr: number;
}

export function generateConvergenceData(): ConvergencePoint[] {
  const points: ConvergencePoint[] = [];
  for (let r = 0; r <= 200; r++) {
    const progress = r / 200;
    const fnr = 0.35 * Math.exp(-3.5 * progress) + 0.02;
    const fpr = 0.25 * Math.exp(-4.0 * progress) + 0.01;
    const noiseScale = 0.008 * (1 - progress);
    points.push({
      round: r,
      fnr: fnr + (Math.random() - 0.5) * noiseScale,
      fpr: fpr + (Math.random() - 0.5) * noiseScale * 0.7,
    });
  }
  return points;
}

export const SATURATION_ROUND = 175;
export const CHART_DATA = generateConvergenceData();
