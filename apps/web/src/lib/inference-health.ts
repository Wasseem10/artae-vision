export type InferenceSummary = {
  samples: number;
  medianMs: number | null;
  p95Ms: number | null;
  processedFps: number | null;
};

/** Device measurements, never detector confidence or accuracy. Bounded memory. */
export class InferenceHealth {
  private samples: { finished: number; latency: number }[] = [];
  add(finished: number, latency: number): InferenceSummary {
    if (!Number.isFinite(finished) || !Number.isFinite(latency) || latency < 0)
      return this.summary();
    if (this.samples.length && finished <= this.samples[this.samples.length - 1].finished)
      return this.summary();
    this.samples.push({ finished, latency });
    if (this.samples.length > 30) this.samples.shift();
    return this.summary();
  }
  summary(): InferenceSummary {
    const n = this.samples.length;
    if (!n) return { samples: 0, medianMs: null, p95Ms: null, processedFps: null };
    const values = this.samples.map(s => s.latency).sort((a, b) => a - b);
    const percentile = (q: number) => {
      const position = (n - 1) * q, lo = Math.floor(position), hi = Math.ceil(position);
      return values[lo] + (values[hi] - values[lo]) * (position - lo);
    };
    const span = this.samples[n - 1].finished - this.samples[0].finished;
    return { samples: n, medianMs: percentile(.5), p95Ms: percentile(.95),
      processedFps: n >= 2 && span > 0 ? (n - 1) * 1000 / span : null };
  }
}
