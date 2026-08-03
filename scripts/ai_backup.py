#!/usr/bin/env python3
"""
Nightly backup of the Ai-Whisperers platform.

What gets backed up:
  1. /root/paragu-ai-platform  → git bundle of the monorepo (all branches + tags, ~MB not GB)
                                    + tar of uncommitted .env files in apps/ for emergency restore
  2. /opt/traefik               → tar of dynamic config + certs (CRITICAL for routing)
  3. /etc/cron.d/ + /etc/logrotate.d/ → our cron + logrotate configs
  4. /var/log/fleet_health.log → fleet probe history (rolling 7 days, captured by logrotate)

What does NOT get backed up (and why):
  - /root/.hermes/   → Hermes has its own state.db + state-snapshots + backups (own DR)
  - node_modules     → reproducible from package-lock/pnpm-lock + npm/pnpm install
  - .next/           → reproducible from source + npm run build
  - dist/            → reproducible from source

Retention: 7 daily + 4 weekly + 3 monthly.
Optional: upload to B2 if B2_BUCKET + B2_KEY_ID + B2_APP_KEY env vars present.
"""
import subprocess, os, sys, time, glob, json, shutil, hashlib, tarfile, io

LOG = "/var/log/ai-backup.log"
DEST = "/var/backups/ai-whisperers"
KEEP_DAILY = 7
KEEP_WEEKLY = 4
KEEP_MONTHLY = 3
LOCK = "/var/run/ai-backup.lock"

def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{ts} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def main():
    if os.path.exists(LOCK):
        try:
            pid = int(open(LOCK).read().strip())
            os.kill(pid, 0)
            log(f"SKIP: backup already running (pid={pid})")
            return
        except (ProcessLookupError, ValueError, FileNotFoundError):
            pass
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))

    try:
        os.makedirs(DEST, exist_ok=True)
        day = time.strftime("%Y-%m-%d")
        day_path = f"{DEST}/{day}"
        os.makedirs(day_path, exist_ok=True)

        manifest = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "archives": [], "size_bytes": 0}

        # 1. Monorepo — git bundle (compact, all branches/tags)
        repo = "/root/paragu-ai-platform"
        bundle = f"{day_path}/paragu-ai-platform.bundle"
        r = subprocess.run(["git", "-C", repo, "bundle", "create", bundle, "--all"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(bundle):
            sha = hashlib.sha256(open(bundle, "rb").read()).hexdigest()
            sz = os.path.getsize(bundle)
            log(f"  OK: monorepo-bundle      {sz/1024/1024:6.1f} MB  sha256={sha[:16]}…")
            manifest["archives"].append({"label": "monorepo-bundle", "path": bundle, "sha256": sha, "size": sz})
            manifest["size_bytes"] += sz
        else:
            log(f"  FAIL: git bundle ({r.stderr[:200]})")

        # 2. Monorepo .env files (per-app, critical for restore) — small tar
        env_tar = f"{day_path}/paragu-ai-platform-envs.tar.gz"
        cmd = ["tar", "-czf", env_tar, "-C", repo,
               "--include=apps/*/.env", "--include=apps/*/.env.local",
               "--include=apps/*/.env.production", "--include=.env",
               "--exclude=*node_modules*", "--exclude=*.bak"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(env_tar):
            sha = hashlib.sha256(open(env_tar, "rb").read()).hexdigest()
            sz = os.path.getsize(env_tar)
            log(f"  OK: monorepo-envs        {sz/1024:6.1f} KB  sha256={sha[:16]}…")
            manifest["archives"].append({"label": "monorepo-envs", "path": env_tar, "sha256": sha, "size": sz})
            manifest["size_bytes"] += sz

        # 3. Traefik
        traefik_tar = f"{day_path}/traefik.tar.gz"
        if os.path.isdir("/opt/traefik"):
            r = subprocess.run(["tar", "-czf", traefik_tar, "-C", "/", "opt/traefik"],
                               capture_output=True, text=True)
            sha = hashlib.sha256(open(traefik_tar, "rb").read()).hexdigest()
            sz = os.path.getsize(traefik_tar)
            log(f"  OK: traefik              {sz/1024:6.1f} KB  sha256={sha[:16]}…")
            manifest["archives"].append({"label": "traefik", "path": traefik_tar, "sha256": sha, "size": sz})
            manifest["size_bytes"] += sz

        # 4. Cron + logrotate configs
        cfgs_tar = f"{day_path}/system-configs.tar.gz"
        cmd = ["tar", "-czf", cfgs_tar, "-C", "/", "etc/cron.d", "etc/logrotate.d"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(cfgs_tar):
            sha = hashlib.sha256(open(cfgs_tar, "rb").read()).hexdigest()
            sz = os.path.getsize(cfgs_tar)
            log(f"  OK: system-configs       {sz/1024:6.1f} KB  sha256={sha[:16]}…")
            manifest["archives"].append({"label": "system-configs", "path": cfgs_tar, "sha256": sha, "size": sz})
            manifest["size_bytes"] += sz

        # 5. Fleet health log (rolling)
        if os.path.exists("/var/log/fleet_health.log"):
            log_copy = f"{day_path}/fleet-health-log.txt"
            shutil.copy("/var/log/fleet_health.log", log_copy)

        # 6. Optional B2 upload
        if os.environ.get("B2_BUCKET"):
            try:
                upload_to_b2(day_path, manifest)
            except Exception as e:
                log(f"  WARN: B2 upload failed: {e}")

        # Write manifest
        with open(f"{day_path}/manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        log(f"DONE: {day} total {manifest['size_bytes']/1024/1024:.1f} MB in {len(manifest['archives'])} archives")

        prune_old_backups()
    finally:
        try: os.remove(LOCK)
        except: pass

def upload_to_b2(day_path, manifest):
    """Offsite R2/B2 upload via custom S3-compatible uploader."""
    r2_script = "/root/.hermes/scripts/r2_upload.py"
    if not os.path.exists(r2_script):
        log("  (R2 uploader missing)")
        return
    log(f"  uploading to offsite R2…")
    subprocess.run(["python3", r2_script, day_path], timeout=1800)

def prune_old_backups():
    if not os.path.isdir(DEST): return
    dirs = sorted(glob.glob(f"{DEST}/????-??-??"), reverse=True)
    if not dirs: return
    daily = dirs[:KEEP_DAILY]
    seen_w = set(); weekly = []
    for d in dirs[KEEP_DAILY:]:
        dt = time.strptime(os.path.basename(d), "%Y-%m-%d")
        wk = time.strftime("%G-W%V", dt)
        if wk not in seen_w:
            seen_w.add(wk); weekly.append(d)
        if len(weekly) >= KEEP_WEEKLY: break
    seen_m = set(); monthly = []
    for d in dirs[KEEP_DAILY + len(weekly):]:
        dt = time.strptime(os.path.basename(d), "%Y-%m-%d")
        mo = time.strftime("%Y-%m", dt)
        if mo not in seen_m:
            seen_m.add(mo); monthly.append(d)
        if len(monthly) >= KEEP_MONTHLY: break
    keep = set(daily) | set(weekly) | set(monthly)
    pruned = sum(1 for d in dirs if d not in keep and not shutil.rmtree(d, ignore_errors=True) is None)
    if pruned:
        log(f"  Pruned {pruned} old backup dirs (kept daily={len(daily)} weekly={len(weekly)} monthly={len(monthly)})")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
