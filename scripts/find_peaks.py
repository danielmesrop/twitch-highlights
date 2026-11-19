#!/usr/bin/env python3
"""Find highlight candidates in a stream's audio: moments that are much louder
than the surrounding minutes (yelling, screaming, laughing, big reactions).

Usage:
    find_peaks.py AUDIO [--top 15] [--pre 20] [--post 10] [--min-gap 90] [--offset 0]

AUDIO is any file ffmpeg can read. --offset is added to every timestamp (use it
when AUDIO is a section that starts partway into the VOD).
Output (stdout): JSON list sorted by score, each {peak, start, end, score, db}.
Times are seconds into the VOD. Progress goes to stderr.
"""
import argparse, json, subprocess, sys
import numpy as np

SR = 8000

def load(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def rolling_median(x, win):
    # median over a centered window, computed on a coarse grid for speed
    half = win // 2
    out = np.empty_like(x)
    step = max(1, win // 20)
    pts = np.arange(0, len(x), step)
    meds = np.array([np.median(x[max(0, i - half): i + half + 1]) for i in pts])
    return np.interp(np.arange(len(x)), pts, meds)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--pre", type=float, default=20, help="seconds of build-up before the peak")
    ap.add_argument("--post", type=float, default=10, help="seconds of reaction after the peak")
    ap.add_argument("--min-gap", type=float, default=90, help="min seconds between two highlights")
    ap.add_argument("--offset", type=float, default=0)
    a = ap.parse_args()

    x = load(a.audio)
    n = len(x) // SR
    if n < 30:
        sys.exit("audio too short")
    # loudness per second, in dB
    sec = x[: n * SR].reshape(n, SR)
    db = 20 * np.log10(np.sqrt((sec ** 2).mean(axis=1)) + 1e-6)
    # sustained loudness: mean over 4 s
    k = 4
    sus = np.convolve(db, np.ones(k) / k, mode="same")
    # compare against the typical level of the surrounding 3 minutes
    base = rolling_median(db, 180)
    spread = rolling_median(np.abs(db - base), 180) + 0.5
    score = (sus - base) / spread
    # ignore silence (stream starting/ending screens, BRB)
    score[base < -50] = 0
    # edges have no surrounding context
    score[:k + 1] = 0
    score[-(k + 1):] = 0

    picks = []
    for i in np.argsort(score)[::-1]:
        if score[i] <= 1.5 or len(picks) >= a.top:
            break
        if all(abs(i - p) >= a.min_gap for p in picks):
            picks.append(int(i))
    out = []
    for i in picks:
        t = i + a.offset
        out.append({"peak": round(t, 1), "start": round(max(a.offset, t - a.pre), 1),
                    "end": round(min(n + a.offset, t + a.post), 1),
                    "score": round(float(score[i]), 2), "db": round(float(db[i]), 1)})
    print(f"{n}s analysed, {len(out)} candidates", file=sys.stderr)
    json.dump(out, sys.stdout, indent=1)
    print()

if __name__ == "__main__":
    main()
