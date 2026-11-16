"""Opaque registered acquisition only. No XML parser, layout or target access."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import urllib.parse
import urllib.request
import uuid

from .cache import ReadLease, canonical_json, strict_json, confined_path, reject_reparse, HEX64

CATALOG_KEYS={'schema_version','provider','raw_root','metadata_overlap_receipt_digest','fixtures'}
FIXTURE_KEYS={'fixture_id','canonical_fixture_id','duplicate_group','role','fps','license','metadata','tracking'}
SOURCE_KEYS={'kind','relative_path','source_url','bytes','sha256','md5'}
FIXTURES={'J03WOH':'train','J03WOY':'train','J03WPY':'selection','J03WN1':'test','J03WQQ':'test'}


def registered_sources(study: Path):
    from .guard import load_registered_study
    manifest=load_registered_study(Path(study))
    with ReadLease(Path(manifest['catalog_path'])) as held:
        if held.size>1_048_576 or held.sha256()!=manifest['catalog_digest']: raise ValueError('catalog integrity mismatch')
        catalog=strict_json(held.read())
    if type(catalog) is not dict or set(catalog)!=CATALOG_KEYS or catalog['schema_version']!=1 or catalog['provider']!='IDSSE' or catalog['raw_root']!=manifest['raw_root'] or not HEX64.fullmatch(str(catalog['metadata_overlap_receipt_digest'])) or type(catalog['fixtures']) is not dict or set(catalog['fixtures'])!=set(FIXTURES):
        raise ValueError('closed complete catalog required')
    names=set(); groups={}; canonical=set()
    for fixture,item in catalog['fixtures'].items():
        if type(item) is not dict or set(item)!=FIXTURE_KEYS or item['fixture_id']!=fixture or item['role']!=FIXTURES[fixture] or type(item['fps']) not in (int,float) or abs(item['fps']-25)>1e-6:
            raise ValueError('fixture schema/role mismatch')
        if type(item['license']) is not dict or set(item['license'])!={'spdx','attribution_receipt_digest'} or item['license']['spdx']!='CC-BY-4.0' or not HEX64.fullmatch(str(item['license']['attribution_receipt_digest'])):
            raise ValueError('license attribution required')
        if not item['duplicate_group'] or not item['canonical_fixture_id'] or item['canonical_fixture_id'] in canonical:
            raise ValueError('invalid/duplicate fixture identity')
        canonical.add(item['canonical_fixture_id'])
        old=groups.setdefault(item['duplicate_group'],item['role'])
        if old!=item['role']: raise ValueError('duplicate group crosses roles')
        for kind in ('metadata','tracking'):
            record=item[kind]
            if type(record) is not dict or set(record)!=SOURCE_KEYS or record['kind']!=kind or type(record['bytes']) is not int or record['bytes']<=0 or not HEX64.fullmatch(str(record['sha256'])) or type(record['md5']) is not str or len(record['md5'])!=32 or any(c not in '0123456789abcdef' for c in record['md5']):
                raise ValueError('complete source integrity required')
            confined_path(Path(catalog['raw_root']),record['relative_path'])
            name=record['relative_path'].casefold()
            if name in names: raise ValueError('aliased catalog filename')
            names.add(name)
            url=urllib.parse.urlsplit(record['source_url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError('HTTPS public source URL required')
    return manifest,catalog


def fetch_registered_sources(study: Path,fixtures: tuple[str,...],destination: Path) -> Path:
    if type(fixtures) is not tuple or not fixtures or len(set(fixtures))!=len(fixtures) or any(x not in FIXTURES for x in fixtures):
        raise PermissionError('explicit allocated fixture allowlist required')
    manifest,catalog=registered_sources(study)
    destination=Path(destination).absolute(); reject_reparse(destination)
    if destination!=Path(manifest['raw_root']): raise ValueError('destination must equal registered raw_root')
    records=[]
    for fixture in fixtures:
        for kind in ('metadata','tracking'):
            record=catalog['fixtures'][fixture][kind]; path=confined_path(destination,record['relative_path'])
            reused=path.exists()
            if reused:
                with ReadLease(path) as lease: lease.verify(record)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                partial=path.with_name(path.name+'.partial-'+uuid.uuid4().hex)
                sha=hashlib.sha256(); md5=hashlib.md5(); total=0
                request=urllib.request.Request(record['source_url'],headers={'User-Agent':'possession-v3-registered-opaque/1.0'})
                with urllib.request.urlopen(request,timeout=120) as response, partial.open('xb') as target:
                    if urllib.parse.urlsplit(response.geturl()).scheme!='https': raise ValueError('insecure transport redirect')
                    for chunk in iter(lambda:response.read(1024*1024),b''):
                        total+=len(chunk)
                        if total>record['bytes']: raise ValueError('download exceeds registered size')
                        target.write(chunk); sha.update(chunk); md5.update(chunk)
                    target.flush(); os.fsync(target.fileno())
                if total!=record['bytes'] or sha.hexdigest()!=record['sha256'] or md5.hexdigest()!=record['md5']:
                    raise ValueError('download integrity failed; original/partial retained')
                with ReadLease(partial) as held: held.verify(record)
                partial.rename(path) # Windows no-replace publication; never overwrite originals.
            records.append({'fixture_id':fixture,'kind':kind,'relative_path':record['relative_path'],'bytes':record['bytes'],
                            'sha256':record['sha256'],'md5':record['md5'],'reused':reused})
    receipt=Path(study).parent/('fetch-'+uuid.uuid4().hex+'.json')
    with receipt.open('xb') as target:
        target.write(canonical_json({'schema_version':1,'kind':'v3-opaque-fetch','catalog_digest':manifest['catalog_digest'],'sources':records,'records_parsed':False})); target.flush(); os.fsync(target.fileno())
    return receipt
