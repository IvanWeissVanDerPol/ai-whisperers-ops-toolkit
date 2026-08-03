#!/usr/bin/env python3
"""
Image optimization sweep v2 — finds and converts oversized images.

Three classes of issues it catches:
  1. PNGs > 500KB with no WebP counterpart → convert
  2. JPGs > 200KB → convert to WebP
  3. PNGs > 1MB even if WebP exists (huge originals waste disk)

Usage:
  python3 /root/.hermes/scripts/image_sweep.py [--apply] [--report-only]

Without --apply: dry-run, generates report only.
With --apply: actually writes the new .webp files.
"""
import os, sys, subprocess, glob, json
from datetime import datetime

APPS_ROOT = "/root/paragu-ai-platform/apps"
PNG_THRESHOLD = 500  # KB
JPG_THRESHOLD = 200  # KB
HUGE_PNG_THRESHOLD = 1024  # KB
QUALITY = 85
APPLY = "--apply" in sys.argv

def main():
    mode = "APPLY" if APPLY else "DRY-RUN"
    print(f"=== Image sweep v2 ({mode}) ===\n")
    findings = []
    apps = sorted([d for d in os.listdir(APPS_ROOT) if os.path.isdir(f"{APPS_ROOT}/{d}")])
    for app in apps:
        public_dir = f"{APPS_ROOT}/{app}/public"
        if not os.path.isdir(public_dir): continue
        for path in glob.glob(f"{public_dir}/**/*", recursive=True):
            if not os.path.isfile(path): continue
            if "/node_modules/" in path or "/.next/" in path: continue
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            sz_kb = os.path.getsize(path) / 1024
            webp = path.rsplit(".", 1)[0] + ".webp"
            webp_exists = os.path.exists(webp)
            # Decide if this needs action
            action = None
            if ext in ("png", "jpeg") and sz_kb > HUGE_PNG_THRESHOLD:
                action = "huge-png"
            elif ext == "png" and sz_kb > PNG_THRESHOLD and not webp_exists:
                action = "no-webp-counterpart"
            elif ext in ("jpg", "jpeg") and sz_kb > JPG_THRESHOLD:
                action = "big-jpg"
            if not action:
                continue
            if APPLY:
                # Convert
                r = subprocess.run(
                    ["convert", path, "-quality", str(QUALITY), "-define", "webp:method=6", webp],
                    capture_output=True, text=True
                )
                ok = r.returncode == 0 and os.path.exists(webp)
                if ok:
                    new_sz = os.path.getsize(webp) / 1024
                else:
                    new_sz = sz_kb
            else:
                # Estimate
                new_sz = sz_kb * 0.15  # typical 85% reduction for WebP
            findings.append({
                "app": app,
                "original": path.replace(APPS_ROOT + "/", ""),
                "webp": webp.replace(APPS_ROOT + "/", "") if APPLY or webp_exists else webp.replace(APPS_ROOT + "/", "") + " (would be created)",
                "action": action,
                "original_kb": round(sz_kb, 1),
                "webp_kb": round(new_sz, 1) if APPLY else round(new_sz, 1),
                "savings_pct": round(100 * (1 - new_sz / sz_kb), 1),
            })
    if not findings:
        print("✅ No oversized images found. All assets are already optimized.")
        return
    findings.sort(key=lambda r: r["savings_pct"], reverse=True)
    total_orig = sum(f["original_kb"] for f in findings)
    total_new = sum(f["webp_kb"] for f in findings)
    total_savings = total_orig - total_new
    print(f"\n=== Summary ===")
    print(f"Files: {len(findings)} | {total_orig/1024:.1f}MB → {total_new/1024:.1f}MB | Saved {total_savings/1024:.1f}MB ({100*total_savings/total_orig:.0f}%)")
    # Group by action
    from collections import Counter
    by_action = Counter(f["action"] for f in findings)
    print(f"By action: {dict(by_action)}")
    # Top 10 wins
    print(f"\nTop 10 wins:")
    for f in findings[:10]:
        rel = f["original"].replace(f"apps/{f['app']}/", "")
        print(f"  [{f['action']:22}] {f['app']:25} {rel:40} {f['original_kb']:>6.0f}KB → {f['webp_kb']:>5.0f}KB ({f['savings_pct']:>4.1f}%)")
    # Save report
    os.makedirs(f"/root/.hermes/analysis/{datetime.now().strftime('%Y-%m-%d')}", exist_ok=True)
    report = f"/root/.hermes/analysis/{datetime.now().strftime('%Y-%m-%d')}/image-sweep-v2.md"
    with open(report, "w") as f:
        f.write(f"# Image Sweep v2 ({mode})\n\n")
        f.write(f"Files: {len(findings)} | {total_orig/1024:.1f}MB → {total_new/1024:.1f}MB\n\n")
        f.write("| Action | App | File | Original | WebP | Savings |\n|---|---|---|---|---|---|\n")
        for f2 in findings:
            rel = f2["original"].replace(f"apps/{f2['app']}/", "")
            f.write(f"| {f2['action']} | {f2['app']} | {rel} | {f2['original_kb']:.0f}KB | {f2['webp_kb']:.0f}KB | {f2['savings_pct']:.1f}% |\n")
    print(f"\nReport: {report}")
    if not APPLY:
        print("\nRe-run with --apply to actually generate the .webp files.")

if __name__ == "__main__":
    main()
