"""Prepare v3 registration metadata without downloading or parsing tracking.

Only public match-information identity fields are processed locally. Console
output is aggregate only. The historical research catalog is never modified.
Independent registration acceptance must check these generated artifacts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ("J03WOH", "J03WOY", "J03WPY", "J03WN1", "J03WQQ")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write_once(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Existing registration preparation artifact differs")
        return
    with path.open("xb") as stream:
        stream.write(data)


def prepare():
    research_path = ROOT / "research/v3/data/dataset-catalog.json"
    research_bytes = research_path.read_bytes()
    research = json.loads(research_bytes)
    dataset = next(row for row in research["datasets"] if row["id"] == "idsse")
    remote_path = ROOT / "local/v3-root-research-verification/figshare-manifest-root.json"
    remote = {row["name"]: row for row in json.loads(remote_path.read_bytes())["files"]}
    metadata_receipt_path = ROOT / "reports/v3-registration-metadata-integrity.json"
    verified = {row["fixture"]: row for row in json.loads(metadata_receipt_path.read_bytes())["files"]}
    protocol = json.loads((ROOT / "specs/003-possession-improvements/protocol.json").read_bytes())
    roles = {fixture: role for role in ("train", "selection", "test")
             for fixture in protocol["split"][role]}
    if set(roles) != set(FIXTURES):
        raise ValueError("Unexpected registered cohort")
    challenge_path = ROOT / "more-than-a-hack-2027-main/DATA.md"
    challenge = challenge_path.read_text(encoding="utf-8")
    if "2024-25" not in challenge or "FC Barcelona vs Athletic Club" not in challenge:
        raise ValueError("Public challenge identity authority changed")

    identities, records = [], {}
    for fixture in FIXTURES:
        original = next(row for row in dataset["matches"] if row["id"] == fixture)
        info = verified[fixture]
        body = (ROOT / info["local_path"]).read_bytes()
        if len(body) != info["bytes"] or sha(body) != info["sha256"]:
            raise ValueError("Metadata integrity changed")
        if hashlib.md5(body).hexdigest() != info["md5"]:
            raise ValueError("Metadata source digest changed")
        general = [node for node in ET.fromstring(body).iter()
                   if node.tag.rsplit("}", 1)[-1] == "General"]
        if len(general) != 1:
            raise ValueError("Metadata identity schema mismatch")
        fields = general[0].attrib
        match_id = fields.get("MatchId")
        if match_id != "DFL-MAT-" + fixture:
            raise ValueError("Metadata fixture identity mismatch")
        kickoff = dt.datetime.fromisoformat(fields["KickoffTime"].replace("Z", "+00:00"))
        if kickoff.tzinfo is None or kickoff.year not in (2022, 2023):
            raise ValueError("Metadata season identity differs")
        home, away = fields.get("HomeTeamId"), fields.get("GuestTeamId")
        if not home or not away or home == away:
            raise ValueError("Metadata team identities invalid")
        group = sha(encoded({"kickoff_utc": kickoff.astimezone(dt.timezone.utc).isoformat(),
                             "home": home, "away": away}))
        canonical = "IDSSE:" + match_id
        identities.append({"fixture_id": fixture, "canonical_fixture_id": canonical,
                           "duplicate_group": group, "expected_match_id": True,
                           "external_season_2022_23": True})
        files = {}
        for kind in ("metadata", "tracking"):
            entry = original[kind]
            authority = remote[entry["file"]]
            expected_sha = info["sha256"] if kind == "metadata" else entry["sha256"]
            if authority["size"] != entry["bytes"]:
                raise ValueError("Pinned public source size differs")
            expected_md5 = authority["computed_md5"]
            if kind == "metadata" and expected_md5 != info["md5"]:
                raise ValueError("Pinned public metadata differs")
            if kind == "tracking" and expected_md5 != entry["figshare_md5"]:
                raise ValueError("Pinned public tracking integrity differs")
            files[kind] = {"kind": kind, "relative_path": f"{fixture}/{entry['file']}",
                           "source_url": authority["download_url"], "bytes": entry["bytes"],
                           "sha256": expected_sha, "md5": expected_md5}
        records[fixture] = {"fixture_id": fixture, "canonical_fixture_id": canonical,
                            "duplicate_group": group, "role": roles[fixture],
                            "fps": 25, **files}

    if len({row["duplicate_group"] for row in identities}) != len(FIXTURES):
        raise ValueError("Duplicate registered fixture identities")
    attribution = {"schema_version": 1, "spdx": "CC-BY-4.0",
                   "credit": "Deutsche Fussball Liga (DFL)",
                   "citation": "Bassek, Rein, Weber and Memmert (2025)",
                   "paper": "https://doi.org/10.1038/s41597-025-04505-y",
                   "dataset": "https://doi.org/10.6084/m9.figshare.28196177.v1",
                   "license": "https://creativecommons.org/licenses/by/4.0/",
                   "adaptation": "Local feature extraction and deterministic synthetic corruption"}
    attribution_path = ROOT / "reports/v3-source-attribution.json"
    write_once(attribution_path, attribution)
    attribution_digest = sha(attribution_path.read_bytes())
    overlap = {"schema_version": 1, "scope": "Public metadata identity only; no tracking/targets parsed",
               "research_catalog_sha256": sha(research_bytes),
               "public_source_manifest_sha256": sha(remote_path.read_bytes()),
               "metadata_integrity_receipt_sha256": sha(metadata_receipt_path.read_bytes()),
               "public_challenge_metadata_sha256": sha(challenge_path.read_bytes()),
               "identities": identities, "unique_duplicate_groups": True,
               "challenge_overlap_excluded_by_disjoint_public_seasons": True,
               "tracking_records_parsed": 0, "target_records_parsed": 0,
               "limitations": "Metadata identity check; no raw-position completeness or scientific acceptance"}
    overlap_path = ROOT / "reports/v3-metadata-overlap.json"
    write_once(overlap_path, overlap)
    for record in records.values():
        record["license"] = {"spdx": "CC-BY-4.0", "attribution_receipt_digest": attribution_digest}
    catalog = {"schema_version": 1, "provider": "IDSSE",
               "raw_root": str((ROOT / "local/v3-data/originals").resolve()),
               "metadata_overlap_receipt_digest": sha(overlap_path.read_bytes()),
               "fixtures": records}
    output = ROOT / "local/v3-control/catalog-complete.json"
    write_once(output, catalog)
    if research_path.read_bytes() != research_bytes:
        raise ValueError("Historical research catalog changed")
    print(json.dumps({"fixtures": len(FIXTURES), "metadata_identity_checks": "pass",
                      "tracking_records_parsed": 0, "target_records_parsed": 0,
                      "catalog_sha256": sha(output.read_bytes()),
                      "independent_registration_acceptance": "pending"}))


if __name__ == "__main__":
    prepare()
