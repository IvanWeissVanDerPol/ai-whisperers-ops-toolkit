#!/usr/bin/env python3
"""
R2 offsite backup uploader.

Strategy:
  - Files <300MB: use wrangler CLI (no SDK, simple)
  - Files >=300MB: split into 200MB chunks, upload each as separate object
    On restore, reassemble by concatenating parts in order

If R2_ACCESS_KEY_ID + R2_SECRET_ACCESS_KEY are set, uses S3 PUT as
preferred strategy (handles any size). Otherwise falls back to wrangler.

Required env vars (in /root/.hermes/secrets/cloudflare.env, mode 600):
  CLOUDFLARE_API_TOKEN — global API token (used by wrangler)
  CLOUDFLARE_ACCOUNT_ID — Cloudflare account ID
  R2_BUCKET             — bucket name
  Optional: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY for S3 fallback
"""
import os, sys, subprocess, time, hmac, hashlib, urllib.parse, urllib.request, json
from pathlib import Path

LOG_PREFIX = "[R2]"
CHUNK_SIZE = 200 * 1024 * 1024  # 200MB

def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts} {LOG_PREFIX} {msg}", flush=True)

def check_env():
    needed = ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "R2_BUCKET"]
    missing = [k for k in needed if not os.environ.get(k)]
    return missing

def upload_via_wrangler(local_path, bucket, key):
    """Use wrangler for files <300MB (simpler, no signature)."""
    cmd = ["wrangler", "r2", "object", "put",
           f"{bucket}/{key}", "--file", local_path, "--remote"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       env=os.environ.copy())
    return r.returncode == 0, r.stderr

def sign_s3_put(key, body_bytes, content_type="application/octet-stream"):
    access = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not access or not secret: return None
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    endpoint = os.environ.get("R2_ENDPOINT") or f"https://{account}.r2.cloudflarestorage.com"
    host = endpoint.replace("https://", "").replace("http://", "")
    region = "auto"; service = "s3"
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    today = now[:8]
    payload_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"PUT\n/{key}\n\ncontent-type:{content_type}\nhost:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{now}\n"
    string_to_sign = f"AWS4-HMAC-SHA256\n{now}\n{today}/{region}/{service}/aws4_request\n" + hashlib.sha256(canonical.encode()).hexdigest()
    def h(k, m): return hmac.new(k, m.encode(), hashlib.sha256).digest()
    sig = h(hmac.new(("AWS4" + secret).encode(), today.encode(), hashlib.sha256).digest(), f"{region}/{service}/aws4_request")
    sig = h(sig, string_to_sign)
    return {
        "Host": host, "Content-Type": content_type, "x-amz-date": now,
        "x-amz-content-sha256": payload_hash,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access}/{today}/{region}/{service}/aws4_request, SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, Signature={sig.hex()}"
    }

def upload_via_s3(body, bucket, key, content_type="application/octet-stream"):
    headers = sign_s3_put(key, body)
    if not headers: return False, "no S3 creds"
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    endpoint = os.environ.get("R2_ENDPOINT") or f"https://{account}.r2.cloudflarestorage.com"
    url = f"{endpoint}/{bucket}/{urllib.parse.quote(key, safe='/')}"
    req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            if r.status in (200, 204): return True, ""
            return False, f"HTTP {r.status}"
    except Exception as e: return False, str(e)

def upload_file(local_path, bucket, r2_key, force_s3=False):
    """Upload a file, splitting if >300MB."""
    size = os.path.getsize(local_path)
    use_s3 = force_s3 or os.environ.get("R2_ACCESS_KEY_ID")
    if size < 300 * 1024 * 1024:
        # Single shot
        if use_s3:
            body = Path(local_path).read_bytes()
            return upload_via_s3(body, bucket, r2_key)
        else:
            return upload_via_wrangler(local_path, bucket, r2_key)
    # Split into chunks
    log(f"  Splitting {r2_key} ({size/1024/1024:.0f}MB) into 200MB chunks")
    with open(local_path, "rb") as f:
        chunk_idx = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk: break
            part_key = f"{r2_key}.part{chunk_idx:04d}"
            if use_s3:
                ok, err = upload_via_s3(chunk, bucket, part_key)
            else:
                # wrangler doesn't support piping - write to temp
                tmp = f"/tmp/r2chunk.{chunk_idx}"
                with open(tmp, "wb") as tf:
                    tf.write(chunk)
                ok, err = upload_via_wrangler(tmp, bucket, part_key)
                os.unlink(tmp)
            if not ok:
                return False, f"chunk {chunk_idx}: {err[:200]}"
            chunk_idx += 1
    # Write a manifest
    manifest = {"original_key": r2_key, "size": size, "chunks": chunk_idx, "chunk_size": CHUNK_SIZE}
    if use_s3:
        ok, err = upload_via_s3(json.dumps(manifest).encode(), bucket, f"{r2_key}.manifest")
    return ok, err or ""

def main():
    if len(sys.argv) < 2:
        log("Usage: r2_upload.py <backup_dir>")
        sys.exit(0)
    backup_dir = sys.argv[1]
    if not os.path.isdir(backup_dir):
        log(f"Backup dir not found: {backup_dir}")
        sys.exit(0)
    missing = check_env()
    if missing:
        log(f"R2 env not set ({','.join(missing)}) — skipping offsite upload.")
        sys.exit(0)
    day = os.path.basename(backup_dir)
    files = sorted([f for f in os.listdir(backup_dir) if f != "manifest.json"])
    if not files:
        log("No files to upload")
        sys.exit(0)
    bucket = os.environ["R2_BUCKET"]
    ok = 0
    for fn in files:
        local_path = f"{backup_dir}/{fn}"
        size = os.path.getsize(local_path)
        r2_key = f"paragu-ai-backups/{day}/{fn}"
        success, err = upload_file(local_path, bucket, r2_key)
        if success:
            log(f"  OK: {r2_key} ({size/1024/1024:.1f} MB)")
            ok += 1
        else:
            log(f"  FAIL: {r2_key}: {err[:200]}")
    log(f"Uploaded {ok}/{len(files)} archives to R2")
    if ok == len(files):
        try:
            with open(f"{backup_dir}/manifest.json") as f:
                manifest = json.load(f)
            manifest["r2_uploaded"] = ok
            manifest["r2_bucket"] = bucket
            with open(f"{backup_dir}/manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e: log(f"  manifest update failed: {e}")

if __name__ == "__main__":
    main()
