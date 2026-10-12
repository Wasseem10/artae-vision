import { afterEach, describe, expect, it, vi } from "vitest";
import { seekPresentedFrame, validPresentedTime } from "./evaluation-video-frame";

function fakeVideo() {
  const target = new EventTarget();
  let callback: VideoFrameRequestCallback | undefined;
  const cancel = vi.fn();
  const video = Object.assign(target, {
    duration: 10, currentTime: 0,
    requestVideoFrameCallback: vi.fn((next: VideoFrameRequestCallback) => { callback = next; return 7; }),
    cancelVideoFrameCallback: cancel,
  }) as unknown as HTMLVideoElement;
  const present = (mediaTime: number) => callback?.(0, { mediaTime, presentedFrames: 2 } as VideoFrameCallbackMetadata);
  return { video, present, cancel };
}

afterEach(() => vi.useRealTimers());

describe("evaluation presented frames", () => {
  it("waits for presentation even if a seek completes", async () => {
    vi.useFakeTimers();
    const { video, present } = fakeVideo();
    const resolved = vi.fn();
    const pending = seekPresentedFrame(video, 2).then(resolved);
    video.dispatchEvent(new Event("seeked"));
    await Promise.resolve();
    expect(resolved).not.toHaveBeenCalled();
    expect(video.currentTime).toBe(2.001);
    present(2);
    await pending;
    expect(resolved).toHaveBeenCalledWith({ requestedSeconds: 2, decodedSeconds: 2, presentedFrames: 2 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects stale or future decoded frames and cleans callbacks", async () => {
    vi.useFakeTimers();
    for (const decoded of [0, 2.1, Number.NaN]) {
      const { video, present, cancel } = fakeVideo();
      const pending = seekPresentedFrame(video, 2);
      const rejected = expect(pending).rejects.toThrow("Unexpected presented");
      present(decoded);
      await rejected;
      expect(cancel).toHaveBeenCalledWith(7);
      expect(vi.getTimerCount()).toBe(0);
    }
  });

  it("permits frame quantization within 50 ms and retains the actual timestamp", async () => {
    vi.useFakeTimers();
    const { video, present } = fakeVideo();
    const pending = seekPresentedFrame(video, 2);
    present(1.96);
    expect((await pending).decodedSeconds).toBe(1.96);
    expect(validPresentedTime(2, 1.94)).toBe(false);
  });

  it("rejects timeout and a stop request without leaving timers", async () => {
    vi.useFakeTimers();
    let cancelled = false;
    let fixture = fakeVideo();
    let pending = seekPresentedFrame(fixture.video, 2, () => cancelled, 1000);
    let rejected = expect(pending).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(1000);
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    fixture = fakeVideo();
    pending = seekPresentedFrame(fixture.video, 2, () => cancelled);
    rejected = expect(pending).rejects.toThrow("cancelled");
    cancelled = true;
    await vi.advanceTimersByTimeAsync(100);
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
  });

  it("rejects unavailable presentation APIs, invalid samples, and decode errors", async () => {
    vi.useFakeTimers();
    const fixture = fakeVideo();
    const pending = seekPresentedFrame(fixture.video, 2);
    const rejected = expect(pending).rejects.toThrow("decode failed");
    fixture.video.dispatchEvent(new Event("error"));
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    await expect(seekPresentedFrame({ duration: 10 } as HTMLVideoElement, 2)).rejects.toThrow("unavailable");
    await expect(seekPresentedFrame(fixture.video, 10)).rejects.toThrow("invalid");
  });
});
