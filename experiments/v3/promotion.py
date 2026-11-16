"""Write a versioned local disposition receipt; never select the active model."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
from pathlib import Path
import uuid

from . import cache
from .exporting import _held_json,_version_one,verify_science_receipt,verify_code_zip,AUTH_IDENTITIES
from .runner import _write

G08_GATES=frozenset(('fresh_environment','input_to_csv','exact_frame_label_contract','public_bounds',
    'determinism','official_validator','safe_failure','core_equivalence','synthetic_ui','resource_budget',
    'scientific_closure','fallback_preserved'))


def _identity_record(stack,root,record):
    if (type(record) is not dict or set(record)!={'relative_path','bytes','sha256'} or type(record['bytes']) is not int
            or record['bytes']<=0 or type(record['sha256']) is not str or not cache.HEX64.fullmatch(record['sha256'])):
        raise ValueError('exact artifact identity required')
    held=stack.enter_context(cache.ReadLease(cache.confined_path(root,record['relative_path'])))
    held.verify(record)
    return held


def promote(release,science,acceptance,root_verification,receipt):
    from .guard import ROOT
    root=ROOT.absolute(); receipt=Path(receipt).absolute()
    cache.reject_reparse(receipt)
    if (receipt.exists() or not receipt.parent.is_dir() or receipt.suffix!='.json'
            or not receipt.is_relative_to(root/'local/v3-releases')):
        raise ValueError('new versioned local promotion receipt required')
    doc,release_digest=cache._release_document(Path(release))
    with ExitStack() as stack:
        scientific,science_held=_held_json(stack,Path(science))
        identities={key:scientific.get(key) for key in AUTH_IDENTITIES}
        for key,value in doc['provenance'].items():
            if identities[key]!=value: raise ValueError('release/science provenance mismatch')
        verify_science_receipt(stack,root,scientific,identities)
        accepted,acceptance_held=_held_json(stack,Path(acceptance))
        verified,root_held=_held_json(stack,Path(root_verification))
        if (not _version_one(accepted) or accepted.get('scope')!='G08 exact-package acceptance'
                or accepted.get('verdict')!='PASS_BOUNDED' or accepted.get('actual_evidence') is not True
                or accepted.get('release_id')!=doc['release_id'] or accepted.get('release_digest')!=release_digest
                or accepted.get('science_receipt_digest')!=science_held.sha256()):
            raise ValueError('actual exact-release independent acceptance required')
        gates=accepted.get('gates')
        if type(gates) is not dict or set(gates)!=G08_GATES or any(value is not True for value in gates.values()):
            raise ValueError('all G08 acceptance gates required')
        if (not _version_one(verified) or verified.get('scope')!='G08 root verification' or verified.get('root_verified') is not True
                or verified.get('release_digest')!=release_digest or verified.get('science_receipt_digest')!=science_held.sha256()
                or verified.get('acceptance_digest')!=acceptance_held.sha256()):
            raise ValueError('matching root verification required')
        zip_held=_identity_record(stack,root,accepted.get('code_zip'))
        verify_code_zip(zip_held,release)
        if verified.get('code_zip_sha256')!=zip_held.sha256(): raise ValueError('root ZIP mismatch')
        fallback_held=_identity_record(stack,root,verified.get('fallback'))
        if fallback_held.sha256()!=scientific['comparator_digest']:
            raise ValueError('science/fallback manifest mismatch')
        if fallback_held.size>2097152: raise ValueError('oversized fallback manifest')
        fallback_held.seek(0); fallback=cache.strict_json(fallback_held.read())
        records=fallback.get('files')
        if type(records) is not dict or len(records)!=29: raise ValueError('exact fallback29 required')
        for name,record in records.items():
            if (type(record) is not dict or set(record)!={'bytes','sha256'} or type(record['bytes']) is not int
                    or record['bytes']<0 or type(record['sha256']) is not str or not cache.HEX64.fullmatch(record['sha256'])):
                raise ValueError('invalid fallback record')
            held=stack.enter_context(cache.ReadLease(cache.confined_path(root,name))); held.verify(record)
        result={'schema_version':1,'kind':'v3-local-promotion-receipt','release_id':doc['release_id'],
                'release_digest':release_digest,'study_digest':scientific['study_digest'],
                'finalist_digest':scientific['finalist_digest'],'model_seal_digest':scientific['model_seal_digest'],
                'test_result_digest':scientific['test_result_digest'],'code_zip_sha256':zip_held.sha256(),
                'science_receipt_digest':science_held.sha256(),'blind_acceptance_digest':acceptance_held.sha256(),
                'root_verification_digest':root_held.sha256(),'fallback_manifest_digest':fallback_held.sha256(),
                'fallback_files_verified':29,'accepted_default_modified':False,'submitted':False,'published':False}
        stage=receipt.with_name('.partial-v3-promotion-'+uuid.uuid4().hex+'.json')
        _write(stage,cache.canonical_json(result)); stage.rename(receipt)
    return result
