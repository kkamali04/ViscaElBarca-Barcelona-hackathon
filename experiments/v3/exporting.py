"""Explicit allowlisted v3 code ZIPs and private, non-submitted review packs."""
from __future__ import annotations

from contextlib import ExitStack
import ast
import hashlib
import io
from pathlib import Path
import re
import zipfile
import uuid

from . import cache
from .runner import _write, open_generation

ZIP_LIMIT=20971520
MEMBER_LIMIT=50000000
NOTICE_PATHS=frozenset(('experiments/v3/TECHNICAL.md','experiments/v3/REPRODUCE.md',
    'specs/003-possession-improvements/protocol.json','requirements-training-lock.txt',
    'specs/003-possession-improvements/PRD-MULTIMATCH.md','specs/003-possession-improvements/PRD-TURNOVER.md',
    'specs/003-possession-improvements/contracts.md',
    'more-than-a-hack-2027-main/LICENSE'))
REVIEW_PATHS=frozenset(('review_app/__init__.py','review_app/server.py','review_app/state.py',
    'review_app/exporting.py','review_app/static/index.html','review_app/static/app.css','review_app/static/app.js'))
MODEL_DESTINATIONS={'emitter':'models/v3-emitter.json','head':'models/v3-boundary.json','config':'models/v3-candidate.json'}


def _safe_name(name):
    # Reuse unchanged Windows-safe filename rules; never arbitrary project globs.
    from review_app.exporting import _safe_member
    return _safe_member(name)


def zip_bytes(members):
    folded=set(); size=0
    for name,payload in members.items():
        _safe_name(name)
        if name.casefold() in folded or not isinstance(payload,bytes) or len(payload)>=MEMBER_LIMIT:
            raise ValueError('duplicate/oversized ZIP member')
        folded.add(name.casefold()); size+=len(payload)
    if size>250000000: raise ValueError('expanded ZIP exceeds bounded size')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,payload in sorted(members.items()):
            info=zipfile.ZipInfo(name,(2026,11,15,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3; info.external_attr=0o100644<<16
            archive.writestr(info,payload,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    result=buffer.getvalue()
    if len(result)>ZIP_LIMIT: raise ValueError('ZIP exceeds20MiB')
    return result


def write_zip_once(destination,members):
    destination=Path(destination).absolute(); cache.reject_reparse(destination)
    if destination.exists() or not destination.parent.is_dir() or destination.suffix!='.zip':
        raise ValueError('new ZIP in existing trusted directory required')
    _safe_name(destination.name)
    payload=zip_bytes(members)
    temporary=destination.with_name('.partial-v3-'+uuid.uuid4().hex+'.zip')
    _write(temporary,payload)
    temporary.rename(destination)
    return {'path':str(destination),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),
            'submission_ready':False}


def _held_json(stack,path,maximum=2097152):
    held=stack.enter_context(cache.ReadLease(path))
    if held.size>maximum: raise ValueError('oversized release descriptor')
    return cache.strict_json(held.read()),held


def scientific_names(read_source):
    """AST import closure over registered/manifested source bytes, never globs.

    Optional candidate probes are only .py files beneath explicit local module
    namespaces. Known dynamic organizer imports are already minimum roots.
    """
    found=set(); pending=list(cache.REQUIRED_SCIENTIFIC_PATHS)
    release_only={f'experiments/v3/{name}.py' for name in ('runner','exporting','review','promotion')}
    prefixes={'experiments','possession_model','validation','tools','review_app'}
    def consider(name):
        if name in found or name in release_only: return True
        if read_source(name) is not None:
            pending.append(name); return True
        return False
    while pending:
        name=pending.pop()
        if name in found: continue
        payload=read_source(name)
        if payload is None: raise ValueError('required scientific source missing')
        found.add(name)
        if not name.endswith('.py'): continue
        parts=name.split('/')
        # Preserve ordinary package initializers where they actually exist;
        # legitimate namespace packages need no fabricated __init__.py.
        for i in range(1,len(parts)):
            consider('/'.join(parts[:i]+['__init__.py']))
        tree=ast.parse(payload.decode('utf-8-sig'))
        for node in ast.walk(tree):
            modules=[]; required=[]
            if isinstance(node,ast.Import):
                modules=[item.name.split('.') for item in node.names]; required=list(modules)
            elif isinstance(node,ast.ImportFrom):
                if node.level:
                    base=parts[:-node.level]
                    if not base: continue
                    module=base+(node.module.split('.') if node.module else [])
                else: module=node.module.split('.') if node.module else []
                if module:
                    modules=[module]+[module+item.name.split('.') for item in node.names if item.name!='*']
                    required=[module]
            resolved=set()
            for module in modules:
                if not module or module[0] not in prefixes: continue
                direct=consider('/'.join(module)+'.py')
                package=consider('/'.join(module+['__init__.py']))
                if direct or package: resolved.add(tuple(module))
            for module in required:
                if module and module[0] in prefixes and not any(item[:len(module)]==tuple(module) for item in resolved):
                    raise ValueError('unresolved local scientific import')
    return frozenset(found)


def _allowed_names(doc,scientific):
    expected=scientific|cache.REQUIRED_RUNTIME_PATHS|NOTICE_PATHS|REVIEW_PATHS
    return expected|{path for path in doc['models'].values() if path is not None}


def release_members(release):
    """Read a verified exact release under held identities for deterministic export."""
    release=Path(release).absolute(); doc,digest=cache._release_document(release)
    members={}
    with ExitStack() as stack:
        held=stack.enter_context(cache.ReadLease(release))
        if held.sha256()!=digest: raise ValueError('release manifest changed')
        held.seek(0); members['release.json']=held.read()
        for item in doc['files']:
            held=stack.enter_context(cache.ReadLease(cache.confined_path(release.parent,item['relative_path'])))
            held.verify(item); held.seek(0); members[item['relative_path']]=held.read()
        scientific=scientific_names(members.get)
        if ({item['relative_path'] for item in doc['files']}!=_allowed_names(doc,scientific)
                or {item['relative_path'] for item in doc['files'] if item['role']=='scientific'}!=scientific):
            raise ValueError('code-only source/import allowlist differs')
    return members,doc,digest


def export_release(release,destination):
    members,doc,digest=release_members(release)
    result=write_zip_once(destination,members)
    return {**result,'release_id':doc['release_id'],'release_digest':digest,'kind':'v3-code-only'}


def verify_code_zip(held,release):
    expected,doc,digest=release_members(release)
    if held.size>ZIP_LIMIT: raise ValueError('oversized code ZIP')
    held.seek(0)
    with zipfile.ZipFile(held.file) as archive:
        infos=archive.infolist()
        if len(infos)!=len(expected) or {i.filename for i in infos}!=set(expected):
            raise ValueError('code ZIP closure mismatch')
        for info in infos:
            if info.file_size!=len(expected[info.filename]) or info.flag_bits&1 or info.is_dir():
                raise ValueError('invalid code ZIP member')
            if archive.read(info)!=expected[info.filename]: raise ValueError('code ZIP content mismatch')
    # Exact canonical ZIP identity prevents a different envelope being described
    # as the independently accepted deterministic package.
    held.seek(0)
    if held.sha256()!=hashlib.sha256(zip_bytes(expected)).hexdigest(): raise ValueError('noncanonical code ZIP')
    return doc,digest


AUTH_IDENTITIES={'study_digest','finalist_digest','model_seal_digest','protocol_digest',
                 'scientific_closure_digest','comparator_digest','test_result_digest'}
AUTH_PATHS={'study_path','finalist_path','model_seal_path','test_result_path','g07_receipt_path'}
AUTH_KEYS={'schema_version','kind','allow_export','g07_receipt_digest'}|AUTH_IDENTITIES|AUTH_PATHS
SCIENCE_KEYS={'schema_version','kind','gate_passed','independent_report','root_reproduction'}|AUTH_IDENTITIES


def _version_one(document):
    return type(document) is dict and type(document.get('schema_version')) is int and document['schema_version']==1


def verify_science_receipt(stack,root,science,identities):
    if (type(science) is not dict or set(science)!=SCIENCE_KEYS or not _version_one(science)
            or science['kind']!='v3-scientific-acceptance' or science['gate_passed'] is not True):
        raise ValueError('closed successful G07 receipt required')
    if any(science[key]!=identities[key] for key in AUTH_IDENTITIES):
        raise ValueError('G07 receipt identity mismatch')
    for role in ('independent_report','root_reproduction'):
        record=science[role]
        if (type(record) is not dict or set(record)!={'relative_path','bytes','sha256'} or type(record['bytes']) is not int
                or record['bytes']<=0 or type(record['sha256']) is not str or not cache.HEX64.fullmatch(record['sha256'])):
            raise ValueError('G07 evidence record required')
        evidence,held=_held_json(stack,cache.confined_path(root,record['relative_path']))
        held.verify(record)
        if (type(evidence) is not dict or not _version_one(evidence) or evidence.get('scope')!='G07 scientific acceptance'
                or evidence.get('gate_passed') is not True
                or any(evidence.get(key)!=identities[key] for key in ('study_digest','finalist_digest','test_result_digest'))):
            raise ValueError('G07 evidence scope/identity failed')
        if role=='independent_report' and evidence.get('verdict')!='PASS_BOUNDED':
            raise ValueError('independent G07 acceptance absent')
        if role=='root_reproduction' and evidence.get('root_verified') is not True:
            raise ValueError('root G07 reproduction absent')


def _verify_complete_test(study,value,result,final):
    """Require the producer's complete cohort/grid and recompute its verdict."""
    from . import evaluate,guard
    fixtures=guard._config(study,value)['split']['test']
    if (type(fixtures) is not list or len(fixtures)!=2 or len(set(fixtures))!=2
            or any(type(item) is not str or not item for item in fixtures)
            or type(result.get('fixture_ids')) is not list or result['fixture_ids']!=fixtures
            or type(result.get('attempt_id')) is not str or not result['attempt_id'].strip()
            or result['attempt_id']!=result['attempt_id'].strip()
            or type(result.get('limitations')) is not str or not result['limitations'].strip()):
        raise ValueError('complete canonical test cohort envelope required')
    for key,expected in (('fixture_count',2),('N',2),('condition_count',6),('candidate_count',2)):
        if type(result.get(key)) is not int or result[key]!=expected:
            raise ValueError('native fixed test counts required')
    rows=result.get('rows')
    if type(rows) is not list: raise ValueError('complete test rows required')
    for row in rows:
        if (type(row) is not dict or set(row)!={'fixture_id','condition','candidate_id','metrics','prediction_digest'}
                or any(type(row[key]) is not str for key in ('fixture_id','condition','candidate_id','prediction_digest'))
                or not cache.HEX64.fullmatch(row['prediction_digest'])):
            raise ValueError('complete typed test row required')
    # This is the same frozen production gate, rather than a second metric or
    # threshold implementation in the transport layer. Its validator checks the
    # complete unique 2-fixture x 6-condition x 2-candidate grid and finite metrics.
    verdict=evaluate.paired_gate(rows,tuple(fixtures),final['candidate_id'])
    if verdict['gate_passed'] is not True or cache.canonical_json(result['verdict'])!=cache.canonical_json(verdict):
        raise ValueError('recorded test verdict disagrees with frozen paired gate')
    expected={(fixture,condition) for fixture in fixtures for condition in evaluate.CONDITION_IDS}
    inputs=result.get('inputs'); seen=set(); targets={}
    if type(inputs) is not list or len(inputs)!=len(expected): raise ValueError('complete test input grid required')
    for item in inputs:
        if (type(item) is not dict or set(item)!={'fixture_id','condition','observation_digest','target_digest','corruption'}
                or any(type(item[key]) is not str for key in ('fixture_id','condition','observation_digest','target_digest'))
                or any(not cache.HEX64.fullmatch(item[key]) for key in ('observation_digest','target_digest'))
                or type(item['corruption']) is not dict or not item['corruption']):
            raise ValueError('complete typed test input identity required')
        key=(item['fixture_id'],item['condition'])
        if key not in expected or key in seen or targets.setdefault(key[0],item['target_digest'])!=item['target_digest']:
            raise ValueError('test input cohort/condition/target identity mismatch')
        seen.add(key)


def _verify_test_artifacts(stack,study,result,seal,final,seal_held,seal_digest):
    """Verify the actual final-test envelope's complete, canonical lineage."""
    artifacts=result.get('artifacts')
    if (type(artifacts) is not list or not artifacts or type(result.get('artifact_count')) is not int
            or result['artifact_count']!=len(artifacts)):
        raise ValueError('complete test artifact manifest required')
    expected={'models/models.json':{'relative_path':'models/models.json','bytes':seal_held.size,'sha256':seal_digest}}
    for model in seal['models']:
        for record in ({key:model[key] for key in ('relative_path','bytes','sha256')},model['parity_receipt']):
            if record['relative_path'] in expected: raise ValueError('duplicate sealed model lineage')
            expected[record['relative_path']]=record
    selection=stack.enter_context(cache.ReadLease(study.parent/'selection/result.json'))
    expected['selection/result.json']={'relative_path':'selection/result.json','bytes':selection.size,
                                       'sha256':final['selection_receipt_digest']}
    seen=set()
    for record in artifacts:
        if (type(record) is not dict or set(record)!={'relative_path','bytes','sha256'}
                or type(record['bytes']) is not int or record['bytes']<=0
                or type(record['sha256']) is not str or not cache.HEX64.fullmatch(record['sha256'])):
            raise ValueError('closed typed test artifact identity required')
        path=cache.confined_path(study.parent,record['relative_path'])
        name=record['relative_path']
        if path in seen or name not in expected or record!=expected[name]:
            raise ValueError('test artifact lineage mismatch')
        seen.add(path)
        held=seal_held if name=='models/models.json' else selection if name=='selection/result.json' else stack.enter_context(cache.ReadLease(path))
        held.verify(record)
    if len(seen)!=len(expected): raise ValueError('incomplete test artifact lineage')


def _authorize_export(stack,finalist,root):
    from . import guard
    if root.resolve()!=guard.ROOT.resolve(): raise ValueError('registered project root required')
    finalist=Path(finalist).absolute(); cache.reject_reparse(finalist)
    authorization,held=_held_json(stack,finalist.parent/'release/export-authorization.json')
    if (type(authorization) is not dict or set(authorization)!=AUTH_KEYS or not _version_one(authorization)
            or authorization['kind']!='v3-export-authorization' or authorization['allow_export'] is not True):
        raise ValueError('closed post-G07 export authorization required')
    for key in AUTH_IDENTITIES|{'g07_receipt_digest'}:
        if type(authorization[key]) is not str or not cache.HEX64.fullmatch(authorization[key]):
            raise ValueError('invalid authorization digest')
    paths={key:cache.confined_path(root,authorization[key]) for key in AUTH_PATHS}
    study=paths['study_path']
    expected={'study_path':finalist.parent/'study.json','finalist_path':finalist,
              'model_seal_path':finalist.parent/'models/models.json','test_result_path':finalist.parent/'test/result.json'}
    if finalist.name!='finalist.json' or any(paths[key]!=path for key,path in expected.items()):
        raise ValueError('noncanonical authorization layout')
    held_paths={}
    for key,path in paths.items():
        source=stack.enter_context(cache.ReadLease(path))
        digest_key=key.replace('_path','_digest')
        if source.sha256()!=authorization[digest_key]: raise ValueError('authorized artifact changed')
        held_paths[key]=source
    value=guard.load_registered_study(study)
    seal=guard.load_model_seal(study)
    guard._validate_finalist(study,value)
    final,_=_held_json(stack,finalist)
    if any(value[key]!=authorization[key] for key in ('protocol_digest','scientific_closure_digest','comparator_digest')):
        raise ValueError('authorization/study binding mismatch')
    result,_=_held_json(stack,paths['test_result_path'])
    if (not _version_one(result) or result.get('status')!='complete' or result.get('gate_passed') is not True
            or result.get('sealed') is not True or result.get('role')!='test'
            or type(result.get('verdict')) is not dict or result['verdict'].get('gate_passed') is not True
            or result.get('candidate_id')!=final['candidate_id']
            or any(result.get(key)!=authorization[key] for key in ('study_digest','finalist_digest'))
            or any(result.get(key)!=value[key] for key in ('protocol_digest','catalog_digest',
                'scientific_closure_digest','environment_digest','comparator_digest'))):
        raise ValueError('complete bound passing test result required')
    _verify_complete_test(study,value,result,final)
    _verify_test_artifacts(stack,study,result,seal,final,held_paths['model_seal_path'],authorization['model_seal_digest'])
    science,_=_held_json(stack,paths['g07_receipt_path'])
    verify_science_receipt(stack,root,science,authorization)
    return authorization,value,seal,final,study


def build_release(finalist,destination,root):
    """Publish a new extracted package only after canonical G07 authorization."""
    root=Path(root).absolute(); destination=Path(destination).absolute()
    cache.reject_reparse(destination)
    if destination.exists() or not destination.parent.is_dir() or not destination.is_relative_to(root/'local/v3-releases'):
        raise ValueError('absent package directory under local/v3-releases required')
    with ExitStack() as stack:
        authorization,value,seal,final,study=_authorize_export(stack,finalist,root)
        provenance={key:authorization[key] for key in ('study_digest','model_seal_digest','finalist_digest','protocol_digest')}
        frozen_by_name={r['relative_path']:r for r in value['artifact_bindings']}
        if not cache.REQUIRED_SCIENTIFIC_PATHS.issubset(frozen_by_name):
            raise ValueError('registered scientific closure incomplete for release')
        bound_sources={}
        def read_registered(name):
            if name in bound_sources: return bound_sources[name]
            path=cache.confined_path(root,name)
            if name not in frozen_by_name:
                if path.is_file(): raise ValueError('import-reachable source absent from prefit registration')
                return None
            held=stack.enter_context(cache.ReadLease(path)); held.verify(frozen_by_name[name])
            held.seek(0); bound_sources[name]=held.read(); return bound_sources[name]
        scientific=scientific_names(read_registered)
        row=final['config']
        candidate={'candidate_id':row['id'],'alpha':row['alpha'],'support':row['support'],'transition_seconds':.5}
        if final['candidate_id']!=row['id']: raise ValueError('finalist candidate mismatch')
        members={}; records=[]
        sources=[(name,'scientific') for name in scientific]
        sources += [(name,'runtime') for name in cache.REQUIRED_RUNTIME_PATHS|REVIEW_PATHS]
        sources += [(name,'notice') for name in NOTICE_PATHS]
        for name,role in sources:
            held=stack.enter_context(cache.ReadLease(cache.confined_path(root,name)))
            if held.size>=MEMBER_LIMIT: raise ValueError('oversized release member')
            if name in frozen_by_name: held.verify(frozen_by_name[name])
            held.seek(0); payload=held.read(); members[name]=payload
            records.append({'relative_path':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'role':role})
        sealed={item['name']:item for item in seal['models']}
        if row['emitter']=='accepted':
            active_name='models/active.json'
            if active_name not in frozen_by_name: raise ValueError('accepted comparator config missing')
            active,held=_held_json(stack,cache.confined_path(root,active_name)); held.verify(frozen_by_name[active_name])
            emitter_path=cache.confined_path(root,active['model'])
            emitter_record=frozen_by_name.get(active['model'])
            if emitter_record is None or emitter_record['sha256']!=active['model_sha256']:
                raise ValueError('accepted comparator model binding mismatch')
        elif row['emitter'] in ('C0','C1'):
            emitter_record=sealed[row['emitter']]
            emitter_path=cache.confined_path(study.parent,emitter_record['relative_path'])
        else: raise ValueError('undeclared emitter')
        selected={'emitter':(emitter_path,emitter_record)}
        if candidate['alpha']>0:
            selected['head']=(cache.confined_path(study.parent,sealed['boundary']['relative_path']),sealed['boundary'])
        models={'emitter':MODEL_DESTINATIONS['emitter'],'head':MODEL_DESTINATIONS['head'] if candidate['alpha']>0 else None,
                'config':MODEL_DESTINATIONS['config']}
        for role,(path,record) in selected.items():
            held=stack.enter_context(cache.ReadLease(path))
            held.verify(record)
            if held.size>=MEMBER_LIMIT or (role=='head' and held.size>524288): raise ValueError('oversized selected model')
            held.seek(0); payload=held.read(); name=MODEL_DESTINATIONS[role]
            members[name]=payload; models[role]=name
            records.append({'relative_path':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'role':role})
        config_payload=cache.canonical_json(candidate); members[models['config']]=config_payload
        records.append({'relative_path':models['config'],'bytes':len(config_payload),'sha256':hashlib.sha256(config_payload).hexdigest(),'role':'config'})
        records.sort(key=lambda x:x['relative_path'])
        policy={'kind':'challenge','forced_dead':[[110808,113742]]}
        release_id='v3-'+candidate['candidate_id']+'-'+authorization['finalist_digest'][:16]
        doc={'schema_version':1,'kind':'v3-observation-release','release_id':release_id,
             'scientific_digest':cache.digest_json([x for x in records if x['role']=='scientific']),
             'runtime_digest':cache.digest_json(records),'files':records,'policy':policy,
             'policy_digest':cache.digest_json(policy),'candidate':candidate,'models':models,'provenance':provenance}
        if set(doc)!=cache.RELEASE_KEYS: raise ValueError('release wire mismatch')
        # Shared authoritative verifier validates the exact staged release wire.
        stage=destination.parent/('.partial-v3-package-'+uuid.uuid4().hex); stage.mkdir()
        for name,payload in members.items():
            path=cache.confined_path(stage,name); path.parent.mkdir(parents=True,exist_ok=True); _write(path,payload)
        _write(stage/'release.json',cache.canonical_json(doc))
        cache._release_document(stage/'release.json')
        members['release.json']=cache.canonical_json(doc)
        code_zip=zip_bytes(members)  # Enforce exact derivative ZIP cap before publication.
        stage.rename(destination)
    return {'path':str(destination),'release_id':doc['release_id'],'release_digest':hashlib.sha256(members['release.json']).hexdigest(),
            'kind':'v3-extracted-code-package','science_receipt_digest':authorization['g07_receipt_digest'],
            'code_zip_sha256':hashlib.sha256(code_zip).hexdigest(),'code_zip_bytes':len(code_zip),'submission_ready':False}


def build_review_pack(release,generation,code_zip,team_name,repository_url,destination,*,demo=False):
    from review_app.exporting import _team,_repository,_markdown
    if type(demo) is not bool: raise ValueError('demo must be boolean')
    display,slug=_team(team_name); repository=_repository(repository_url)
    with cache.ReadLease(code_zip) as code_held:
        doc,digest=verify_code_zip(code_held,release)
        with open_generation(generation,expected_release=digest) as pair:
            if pair.report.get('synthetic_demo') is not demo: raise ValueError('demo/generation mismatch')
            if pair.report['release_id'] != doc['release_id']: raise ValueError('report release identity mismatch')
            csv_payload=pair.read('csv'); report_payload=pair.read('report')
            code_held.seek(0); code_payload=code_held.read()
            with cache.ReadLease(Path(release).parent/'experiments/v3/TECHNICAL.md') as tech:
                document=tech.read().decode('utf-8')
            replacements={'TEAM_NAME':_markdown(display),'REPOSITORY_URL':repository or 'Pending owner publication'}
            document=re.sub(r'\{\{(TEAM_NAME|REPOSITORY_URL)\}\}',lambda m:replacements[m[1]],document)
            marker='DEMO-' if demo else ''
            generation_dir='generations/'+pair.commit['generation_id']
            members={marker+slug+'.csv':csv_payload,marker+slug+'.md':document.encode(),
                     marker+slug+'-code-only.zip':code_payload,
                     generation_dir+'/'+pair.commit['csv']['filename']:csv_payload,
                     generation_dir+'/'+pair.commit['report']['filename']:report_payload,
                     generation_dir+'/commit.json':cache.canonical_json(pair.commit)}
            manifest={'schema_version':1,'kind':'private-v3-review','private':True,'submitted':False,'submission_ready':False,
                      'synthetic_demo':demo,'release_id':doc['release_id'],'release_digest':digest,
                      'generation_id':pair.commit['generation_id'],'generation_directory':generation_dir,
                      'code_zip_sha256':hashlib.sha256(code_payload).hexdigest(),
                      'team_name':display,'repository_url':repository,'repository_publication_verified':False,
                      'files':{name:{'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()} for name,value in members.items()}}
            members['PRIVATE-REVIEW.json']=cache.canonical_json(manifest)
            members['README.md']=(('# SYNTHETIC DEMO\n\n' if demo else '')+
                '# Private local v3 review pack — NOT SUBMITTED\n\nThe CSV and outer ZIP remain private. '
                'Only the code-only ZIP is eligible for separately authorized publication. '
                'Registration, eligibility, repository verification and competition submission remain owner actions.\n').encode()
            result=write_zip_once(destination,members)
    return {**result,'filename':Path(destination).name,'release_id':doc['release_id'],'release_digest':digest,
            'pending':['Owner review, registration, publication and submission are still required.']}
