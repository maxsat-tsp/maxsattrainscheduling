#!/usr/bin/env python3
"""Download the entitled Linux x86-64 CPLEX installer using IBM's HTTP option.

Pass the academic portal URL supplied by the account owner. Tickets and signed
download URLs are never printed or included in the resulting manifest.
"""
import argparse
import hashlib
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--landing-url", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    landing = urllib.parse.urlsplit(args.landing_url)
    if landing.scheme != "https" or landing.hostname != "www.ibm.com":
        raise SystemExit("Expected the IBM HTTPS academic portal URL")
    query = urllib.parse.parse_qs(landing.query)
    ticket = query["ticket"][0]
    assembly = query["partNumber"][0]
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(endpoint, **params):
        url = "https://www.ibm.com/isc/esd/dswdown/services/" + endpoint + "?" + urllib.parse.urlencode(params)
        with client.open(url, timeout=60) as response:
            return json.load(response)

    session = get("validate", ticket=ticket)
    if session.get("rcVal") != 0 or not session.get("ticketLive"):
        raise SystemExit("The academic download ticket is no longer valid")
    result = get("searchPartNumber", entitlementCode="AI", partNumber=assembly)
    images = []
    for brand in result["brands"]:
        images.extend(brand.get("images", []))
        for item in brand.get("assemblies", []):
            images.extend(item.get("images", []))
    candidates = [image for image in images if "Linux x86-64" in image.get("description", "")
                  and image.get("fileName", "").endswith(".bin")]
    if len(candidates) != 1:
        raise SystemExit("Expected exactly one entitled Linux x86-64 installer")
    image = candidates[0]
    name = image["fileName"]
    if Path(name).name != name:
        raise SystemExit("Unexpected installer filename")
    args.destination.mkdir(parents=True, exist_ok=True)
    output = args.destination / name
    expected = int(image["fileSize"])
    if not output.exists():
        response = get("download", portalCode=session["keyName"], clientID=session["ticketID"],
                       partNumber=image["partNumber"], downloadMethod="HTTP")
        signed_url = response["httpDownloadRequestString"]
        if urllib.parse.urlsplit(signed_url).scheme != "https":
            raise SystemExit("IBM did not return a secure download URL")
        temporary = output.with_suffix(output.suffix + ".part")
        print(f"Downloading {name}, expected_bytes={expected}", flush=True)
        received = 0
        with client.open(signed_url, timeout=120) as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                received += len(chunk)
        if received != expected:
            raise SystemExit(f"Incomplete download: received={received}, expected={expected}")
        temporary.rename(output)
    if output.stat().st_size != expected:
        raise SystemExit("Existing installer does not match the entitled file size")
    digest = hashlib.sha256()
    with output.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    manifest = {
        "file": name, "bytes": expected, "sha256": digest.hexdigest(),
        "description": image["description"], "part_number": image["partNumber"],
        "assembly": assembly, "download_method": "IBM HTTP over HTTPS",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        # Error strings can contain signed URLs. Print only the exception type.
        print(f"IBM HTTP download failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
