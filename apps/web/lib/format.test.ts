import { describe, expect, it } from "vitest";
import { direction, formatDate, formatValue } from "./format";

describe("formatValue", () => {
  it("formats money compactly", () => {
    expect(formatValue(1_925_780_448_223, "usd")).toBe("$1.93T");
    expect(formatValue(-2_500_000, "usd")).toBe("-$2.50M");
    expect(formatValue(12_345, "usd")).toBe("$12.3K");
  });
  it("formats per-share prices", () => {
    expect(formatValue(478.4567, "usd_per_share")).toBe("$478.46");
    expect(formatValue(1234.5, "usd_per_share")).toBe("$1,235");
  });
  it("formats percentages from fractions", () => {
    expect(formatValue(0.1234, "pct")).toBe("12.3%");
    expect(formatValue(0.05, "pct", { signed: true })).toBe("+5.0%");
    expect(formatValue(-0.018, "pct", { signed: true })).toBe("-1.8%");
  });
  it("never shows a model probability as certain", () => {
    expect(formatValue(0.999, "prob", { digits: 0 })).toBe(">99%");
    expect(formatValue(1, "prob", { digits: 0 })).toBe(">99%");
    expect(formatValue(0.001, "prob", { digits: 0 })).toBe("<1%");
    expect(formatValue(0, "prob", { digits: 0 })).toBe("<1%");
    expect(formatValue(0.385, "prob")).toBe("38.5%");
    expect(formatValue(0.99975, "prob")).toBe(">99.9%");
  });
  it("drops the sign when a value rounds to zero", () => {
    expect(formatValue(-0.0004, "pct", { signed: true })).toBe("0.0%");
    expect(formatValue(0.0004, "pct", { signed: true })).toBe("0.0%");
    expect(formatValue(-0.004, "usd_per_share")).toBe("$0.00");
    expect(formatValue(-0.05, "pct")).toBe("-5.0%");
  });
  it("formats multiples and scores", () => {
    expect(formatValue(32.18, "x")).toBe("32.2×");
    expect(formatValue(72.6, "score")).toBe("73");
  });
  it("renders missing values as a dash", () => {
    expect(formatValue(null, "usd")).toBe("—");
    expect(formatValue(Number.NaN, "pct")).toBe("—");
  });
});

describe("helpers", () => {
  it("formats ISO dates in UTC", () => {
    expect(formatDate("2026-09-25")).toBe("Sep 25, 2026");
  });
  it("classifies direction", () => {
    expect(direction(0.1)).toBe("up");
    expect(direction(-0.1)).toBe("down");
    expect(direction(0)).toBe("flat");
    expect(direction(null)).toBe("flat");
  });
});
