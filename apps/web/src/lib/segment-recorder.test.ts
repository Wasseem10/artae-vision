import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startSegmentedRecording, type RecordingState } from "./segment-recorder";

class FakeRecorder {
  state: RecordingState | "inactive" = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  startError = false;
  stopError = false;
  start() { if (this.startError) throw new Error("start failed"); this.state = "recording"; }
  stop() { if (this.stopError) throw new Error("stop failed"); this.state = "inactive"; }
  finish(bytes = "video bytes") {
    this.ondataavailable?.({ data: new Blob([bytes]) });
    this.state = "inactive";
    this.onstop?.();
  }
}

function setup(configure?: (recorder: FakeRecorder) => void) {
  const recorders: FakeRecorder[] = [];
  const trackStop = vi.fn();
  const onSegment = vi.fn(), onFailure = vi.fn(), onState = vi.fn();
  const createRecorder = vi.fn(() => {
    const recorder = new FakeRecorder();
    configure?.(recorder);
    recorders.push(recorder);
    return recorder as unknown as MediaRecorder;
  });
  const recording = startSegmentedRecording({
    stream: { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream,
    mimeType: "video/webm", now: () => Date.now() / 1000,
    onSegment, onFailure, onState, createRecorder,
  });
  return { recording, recorders, trackStop, onSegment, onFailure, onState, createRecorder };
}

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(0); });
afterEach(() => { vi.useRealTimers(); });

describe("segmented recording lifecycle", () => {
  it("rotates standalone segments and flushes the final segment without restarting", () => {
    const run = setup();
    vi.advanceTimersByTime(10000);
    run.recorders[0].finish();
    expect(run.onSegment.mock.calls[0][0]).toMatchObject({ start: 0, duration: 10 });
    expect(run.recorders).toHaveLength(2);
    vi.advanceTimersByTime(2000);
    run.recording.stop();
    expect(run.onState).toHaveBeenLastCalledWith("finalizing");
    run.recorders[1].finish();
    expect(run.onSegment.mock.calls[1][0]).toMatchObject({ start: 10, duration: 2 });
    expect(run.onState).toHaveBeenLastCalledWith("stopped");
    expect(run.recorders).toHaveLength(2);
    expect(run.trackStop).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("freezes the source clock before video teardown and ignores duplicate stop events", () => {
    const run = setup();
    vi.advanceTimersByTime(2000);
    run.recording.stop();
    run.recording.stop();
    vi.setSystemTime(0);
    run.recorders[0].finish();
    run.recorders[0].finish();
    expect(run.onSegment).toHaveBeenCalledOnce();
    expect(run.onSegment.mock.calls[0][0].duration).toBe(2);
    expect(run.trackStop).toHaveBeenCalledOnce();
    expect(run.onFailure).not.toHaveBeenCalled();
  });

  it("keeps earlier footage and final error bytes without restarting a failed recorder", () => {
    const run = setup();
    vi.advanceTimersByTime(10000); run.recorders[0].finish();
    vi.advanceTimersByTime(1000); run.recorders[1].onerror?.();
    run.recorders[1].onerror?.();
    run.recorders[1].finish("recovered partial video");
    vi.advanceTimersByTime(30000);
    expect(run.onSegment).toHaveBeenCalledTimes(2);
    expect(run.createRecorder).toHaveBeenCalledTimes(2);
    expect(run.onFailure).toHaveBeenCalledOnce();
    expect(run.onState).toHaveBeenLastCalledWith("failed");
    expect(run.trackStop).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores late errors from a completed segment", () => {
    const run = setup();
    vi.advanceTimersByTime(10000); run.recorders[0].finish();
    run.recorders[0].onerror?.();
    expect(run.onFailure).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000); run.recording.stop(); run.recorders[1].finish();
    expect(run.onSegment).toHaveBeenCalledTimes(2);
  });

  it("handles constructor rejection without leaking its stream", () => {
    const trackStop = vi.fn(), onFailure = vi.fn();
    const recording = startSegmentedRecording({
      stream: { getTracks: () => [{ stop: trackStop }] } as unknown as MediaStream,
      mimeType: "video/webm", now: () => 0, onSegment: vi.fn(), onState: vi.fn(), onFailure,
      createRecorder: () => { throw new Error("unsupported encoder"); },
    });
    recording.stop();
    expect(trackStop).toHaveBeenCalledOnce();
    expect(onFailure).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("handles start rejection without retrying", () => {
    const run = setup((recorder) => { recorder.startError = true; });
    vi.advanceTimersByTime(30000); run.recording.stop();
    expect(run.createRecorder).toHaveBeenCalledOnce();
    expect(run.onFailure).toHaveBeenCalledOnce();
    expect(run.trackStop).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("continues cleanup when recorder stop throws", () => {
    const run = setup((recorder) => { recorder.stopError = true; });
    vi.advanceTimersByTime(10000); run.recording.stop();
    expect(run.onFailure).toHaveBeenCalledOnce();
    expect(run.trackStop).toHaveBeenCalledOnce();
    expect(run.createRecorder).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("fails closed on empty segments rather than looping with no footage", () => {
    const run = setup();
    vi.advanceTimersByTime(10000); run.recorders[0].finish("");
    expect(run.onFailure).toHaveBeenCalledOnce();
    expect(run.onSegment).not.toHaveBeenCalled();
    expect(run.createRecorder).toHaveBeenCalledOnce();
  });

  it("times out finalization while retaining a late valid segment", () => {
    const run = setup();
    vi.advanceTimersByTime(10000);
    vi.advanceTimersByTime(5000);
    expect(run.onFailure).toHaveBeenCalledOnce();
    expect(run.trackStop).toHaveBeenCalledOnce();
    run.recorders[0].finish();
    expect(run.onSegment.mock.calls[0][0].duration).toBe(10);
    expect(run.createRecorder).toHaveBeenCalledOnce();
    expect(run.onState).toHaveBeenLastCalledWith("failed");
  });

  it("allows a very short stopped session without claiming an encoder error", () => {
    const run = setup();
    vi.advanceTimersByTime(100); run.recording.stop(); run.recorders[0].finish();
    expect(run.onSegment).not.toHaveBeenCalled();
    expect(run.onFailure).not.toHaveBeenCalled();
    expect(run.onState).toHaveBeenLastCalledWith("stopped");
  });
});
