#!/usr/bin/env python3
"""
Per-tenant GA4 property provisioning.

Uses Google Analytics Admin API (v1) to:
  1. Create one GA4 property per app (the 39 client sites)
  2. Create one Data Stream (web) per property
  3. Save the resulting Measurement IDs (G-XXXXXXXXXX) to each app's .env.production

Required setup (one-time, manual):
  1. Create a Google Cloud project at console.cloud.google.com
  2. Enable the "Google Analytics Admin API"
  3. Create a Service Account with "Editor" role on your GA account
  4. Download the service account JSON key
  5. Save it to /root/.hermes/secrets/ga-service-account.json
  6. Set GA_ACCOUNT_ID env var (your numeric GA account, not the property)

Then: `python3 /root/.hermes/scripts/ga_provision.py`

This is a ONE-TIME script. Run it once when setting up, then never again.
"""
import os, sys, json
from pathlib import Path

SERVICE_ACCOUNT_JSON = "/root/.hermes/secrets/ga-service-account.json"
APPS_DIR = "/root/paragu-ai-platform/apps"
APPS_TO_SKIP = {"builder", "site-template", "paragu-ai-builder"}

def check_setup():
    if not os.path.exists(SERVICE_ACCOUNT_JSON):
        print(f"ERROR: Service account JSON not found at {SERVICE_ACCOUNT_JSON}")
        print("""
Setup instructions:
  1. Go to console.cloud.google.com
  2. Create or select a project
  3. APIs & Services > Library > search "Google Analytics Admin API" > Enable
  4. IAM & Admin > Service Accounts > Create Service Account
  5. Name: "ai-ga-provisioner", Grant "Editor" access on your GA account
  6. Done > click the service account > Keys > Add Key > Create new (JSON)
  7. Save the JSON to /root/.hermes/secrets/ga-service-account.json
  8. Add the service account email to your GA property's User Management
     (https://analytics.google.com/ > Admin > Account Access Management)
  9. Set GA_ACCOUNT_ID env var (your numeric GA account, format: 123456789)
""")
        sys.exit(1)
    if not os.environ.get("GA_ACCOUNT_ID"):
        print("ERROR: GA_ACCOUNT_ID env var not set")
        print("This is your numeric Google Analytics account ID, not a property ID")
        print("Find it at: https://analytics.google.com/ > Admin > Account Settings")
        sys.exit(1)

def main():
    check_setup()
    # Lazy import so the missing-creds error is friendly
    from google.analytics.admin import AnalyticsAdminServiceClient
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/analytics.edit"],
    )
    client = AnalyticsAdminServiceClient(credentials=credentials)
    account_id = os.environ["GA_ACCOUNT_ID"]
    print(f"Using GA account: {account_id}")
    # Discover apps
    apps = sorted([d for d in os.listdir(APPS_DIR)
                  if os.path.isdir(f"{APPS_DIR}/{d}") and d not in APPS_TO_SKIP])
    print(f"Found {len(apps)} client apps to provision")
    print("=" * 60)
    results = []
    for i, app in enumerate(apps, 1):
        property_name = f"ParaguAI - {app}"
        # Create property
        try:
            prop = client.create_property(
                parent=f"accounts/{account_id}",
                property={"display_name": property_name, "time_zone": "America/Asuncion",
                          "currency_code": "PYG", "industry_category": "TECHNOLOGY"},
            )
            prop_id = prop.name.split("/")[-1]
            # Create web data stream
            stream = client.create_data_stream(
                parent=prop.name,
                data_stream={"display_name": "Web", "type": "DATA_STREAM_TYPE_WEB",
                             "web_stream_data": {"default_uri": f"https://{app}.paragu-ai.com"}},
            )
            measurement_id = stream.web_stream_data.measurement_id
            # Save to .env.production
            env_path = f"{APPS_DIR}/{app}/.env.production"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    content = f.read()
                # Add or replace NEXT_PUBLIC_GA_ID
                if "NEXT_PUBLIC_GA_ID=" in content:
                    content = re.sub(r"NEXT_PUBLIC_GA_ID=.*", f"NEXT_PUBLIC_GA_ID={measurement_id}", content)
                else:
                    content = f"NEXT_PUBLIC_GA_ID={measurement_id}\n" + content
                with open(env_path, "w") as f:
                    f.write(content)
            else:
                with open(env_path, "w") as f:
                    f.write(f"NEXT_PUBLIC_GA_ID={measurement_id}\n")
            results.append({"app": app, "property_id": prop_id, "measurement_id": measurement_id})
            print(f"  [{i:2}/{len(apps)}] {app:30} → {measurement_id}  (property: {prop_id})")
        except Exception as e:
            print(f"  [{i:2}/{len(apps)}] {app:30} → FAILED: {e}")
            results.append({"app": app, "error": str(e)})
    # Save manifest
    manifest_path = "/root/.hermes/analysis/ga-provision-manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "account_id": account_id, "results": results}, f, indent=2)
    print(f"\nManifest: {manifest_path}")
    print(f"Next step: rebuild + redeploy each app to pick up NEXT_PUBLIC_GA_ID")

if __name__ == "__main__":
    import re, time
    main()
