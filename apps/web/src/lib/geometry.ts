import type { ZonePoint } from "@/lib/types";

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function normalizedPoint(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, "left" | "top" | "width" | "height">,
): ZonePoint {
  if (bounds.width <= 0 || bounds.height <= 0) {
    throw new Error("Zone editor bounds must have positive dimensions.");
  }
  return {
    x: Number(clamp((clientX - bounds.left) / bounds.width).toFixed(4)),
    y: Number(clamp((clientY - bounds.top) / bounds.height).toFixed(4)),
  };
}

export function svgPoints(points: ZonePoint[]): string {
  return points.map((point) => `${point.x * 100},${point.y * 100}`).join(" ");
}

