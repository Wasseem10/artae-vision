import { describe, expect, it } from "vitest";

import { normalizedPoint, svgPoints } from "./geometry";

describe("zone geometry", () => {
  const bounds = { left: 100, top: 50, width: 400, height: 200 };

  it("normalizes pointer coordinates", () => {
    expect(normalizedPoint(300, 100, bounds)).toEqual({ x: 0.5, y: 0.25 });
  });

  it("clamps points to the editor boundary", () => {
    expect(normalizedPoint(0, 500, bounds)).toEqual({ x: 0, y: 1 });
  });

  it("converts normalized points to the SVG view box", () => {
    expect(svgPoints([{ x: 0.2, y: 0.5 }, { x: 0.8, y: 1 }])).toBe("20,50 80,100");
  });
});
