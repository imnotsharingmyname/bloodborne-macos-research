#!/usr/bin/env python3
"""Summarize bbport's opt-in BB_GPU_PROFILE=1 GPU timestamp output.

This is a diagnostic tool, not a performance optimization. Timestamp recording
forces render-pass boundaries in the pinned runtime and may change FPS.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import re

HEADER = re.compile(r"GPU profile:\s*([0-9.]+) ms/frame over ([0-9]+) frames, ([0-9]+) labels")
ENTRY = re.compile(r"^\s*([0-9.]+) ms/frame\s+([0-9.]+)/frame\s+(.+?)\s*$")

def parse(text):
    sections = 0
    frames = 0
    reported_ms = 0.0
    labels = defaultdict(lambda: [0.0, 0.0])
    active_frames = 0
    for line in text.splitlines():
        h = HEADER.search(line)
        if h:
            sections += 1
            active_frames = int(h.group(2))
            frames += active_frames
            reported_ms += float(h.group(1)) * active_frames
            continue
        m = ENTRY.match(line)
        if m and active_frames:
            label = m.group(3)
            labels[label][0] += float(m.group(1)) * active_frames
            labels[label][1] += float(m.group(2)) * active_frames
        elif line.startswith("GPU profile:"):
            active_frames = 0
    return {
        "windows": sections,
        "frames": frames,
        "mean_reported_gpu_ms": reported_ms / frames if frames else 0.0,
        "labels": sorted(
            ((name, values[0] / frames, values[1] / frames) for name, values in labels.items()),
            key=lambda row: row[1], reverse=True,
        ) if frames else [],
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path, help="BloodborneResearch/logs/launch-*.log")
    p.add_argument("--top", type=int, default=20)
    a = p.parse_args()
    report = parse(a.log.read_text(errors="replace"))
    if report["frames"] == 0:
        raise SystemExit("No GPU timestamp windows found. Enable 'Record GPU pass timestamps' and play for >5 seconds.")
    print("Windows:", report["windows"], "Frames:", report["frames"])
    print("Mean reported GPU timestamp time: %.2f ms/frame" % report["mean_reported_gpu_ms"])
    print("GPU timestamp profiling is intrusive: it ends render passes and can perturb performance.")
    print("Use for ranking hotspots, not as a clean FPS benchmark.")
    print("\n%-12s %-13s %s" % ("ms/frame", "events/frame", "GPU pass/operation"))
    for name, ms, events in report["labels"][:max(0, a.top)]:
        print("%-12.3f %-13.2f %s" % (ms, events, name))

if __name__ == "__main__":
    main()
