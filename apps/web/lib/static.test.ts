import { describe, expect, it } from "vitest";
import { isStateful, noteEngineChange, staticFile } from "./static";

// The file names mirror services/engine/tests/test_export_static.py, which checks the exporter writes them.
describe("staticFile", () => {
  it("maps report sections, upper-casing the ticker", () => {
    expect(staticFile("/report/zztec/section/valuation")).toBe("report/ZZTEC/valuation.json");
  });
  it("keys compare and watchlist sets independently of order and case", () => {
    expect(staticFile("/compare?tickers=ZZTEC,zzbnk&range=3y")).toBe("compare/ZZBNK_ZZTEC_3y.json");
    expect(staticFile("/compare?tickers=ZZBNK,ZZTEC")).toBe("compare/ZZBNK_ZZTEC_1y.json");
    expect(staticFile("/watchlist/summary?tickers=ZZTEC,ZZBNK")).toBe("watchlist/ZZBNK_ZZTEC.json");
    expect(staticFile("/watchlist/summary?tickers=")).toBe("watchlist/_empty.json");
  });
  it("maps the track record by kind, profile and ticker", () => {
    expect(staticFile("/track-record?kind=live")).toBe("track-record/live/_all.json");
    expect(staticFile("/track-record?kind=backtest&profile=bank")).toBe("track-record/backtest/bank.json");
    expect(staticFile("/track-record/zztec")).toBe("track-record/ticker/ZZTEC.json");
  });
  it("maps meta, snapshots and alerts", () => {
    expect(staticFile("/health")).toBe("health.json");
    expect(staticFile("/meta/methodology")).toBe("meta/methodology.json");
    expect(staticFile("/snapshot/abc123")).toBe("snapshot/abc123.json");
    expect(staticFile("/alerts")).toBe("alerts/inbox.json");
    expect(staticFile("/alerts/unread")).toBe("alerts/unread.json");
  });
  it("leaves custom queries and refreshed reports to the engine", () => {
    expect(staticFile("/report/ZZTEC/section/peers?peers=ZQT01,ZQT02")).toBeNull();
    expect(staticFile("/report/ZZREI/section/headline")).toBe("report/ZZREI/headline.json");
    noteEngineChange("POST", "/report/zzrei/refresh");
    expect(staticFile("/report/ZZREI/section/headline")).toBeNull();
    expect(staticFile("/report/ZZUTL/section/headline")).toBe("report/ZZUTL/headline.json");
    expect(isStateful("/alerts/unread")).toBe(true);
    expect(isStateful("/compare?tickers=A,B")).toBe(false);
  });
  it("has no answer for requests the demo can't serve", () => {
    expect(staticFile("/report/ZZTEC/valuation/whatif")).toBeNull();
    expect(staticFile("/symbols/search?q=zz")).toBeNull();
  });
});
