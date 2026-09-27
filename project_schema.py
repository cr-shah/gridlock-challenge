"""Lossless ingestion of a validated canonical publication; no database access."""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path

from bson import BSON
from publication_validation import validate_publication

MASTER = 'gridlock_master_projects.json'
ARTIFACTS = (MASTER, 'website_data.json', 'project_explorer.json', 'summary_statistics.json')
# Explicit review gate for this rollout, not a fallback for missing metadata.
EXPECTED = {'projects': 78, 'DESC': 54, 'GPC': 24, 'VERIFIED': 15,
            'ESTIMATED': 44, 'UNRESOLVED': 19, 'Point': 38, 'LineString': 21}


class ValidationError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError('Duplicate JSON keys.')
        result[key] = value
    return result


def _check_json(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or '\x00' in key:
                raise ValidationError('Unsupported BSON field name.')
            _check_json(item)
    elif isinstance(value, list):
        for item in value:
            _check_json(item)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError('Non-finite number.')
    elif isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value < 2**63:
            raise ValidationError('Integer exceeds BSON range.')
    elif value is not None and not isinstance(value, (str, bool)):
        raise ValidationError('Unsupported JSON value.')


def _parse(raw):
    value = json.loads(raw, object_pairs_hook=_object)
    _check_json(value)
    return value


def load_dataset(path):
    """Capture bytes once: validation and construction use the same snapshot."""
    path = Path(path)
    if path.name != MASTER:
        raise ValidationError('Input must be the published canonical master, not legacy demo data.')
    folder = path.parent
    return {'receipt': (folder / 'import_receipt.json').read_bytes(),
            'artifacts': {name: (folder / name).read_bytes() for name in ARTIFACTS}}


def _validate(publication):
    receipt = _parse(publication['receipt'])
    raw = publication['artifacts']
    if set(raw) != set(ARTIFACTS) or set(receipt['artifacts']) != set(ARTIFACTS):
        raise ValidationError('Incomplete or unsupported publication artifact inventory.')
    hashes = {name: sha256(raw[name]).hexdigest() for name in ARTIFACTS}
    if hashes != receipt['artifacts']:
        raise ValidationError('Publication artifact hash mismatch.')
    parsed = {name: _parse(raw[name]) for name in ARTIFACTS}
    master = parsed[MASTER]
    if master['dataset_version'] != '1.0.0' or receipt.get('upstream_manifest_verified') is not True:
        raise ValidationError('Unsupported or upstream-unverified publication.')
    for key in ('dataset_version', 'pipeline_commit', 'generated_at'):
        if not isinstance(master.get(key), str) or not master[key].strip():
            raise ValidationError('Missing publication identity metadata.')
        if receipt.get(key) != master[key] or any(p.get(key) != master[key] for p in parsed.values()):
            raise ValidationError('Mixed publication identities.')
    if not isinstance(receipt.get('imported_at'), str) or not receipt.get('source_product_commit'):
        raise ValidationError('Missing receipt provenance.')
    for timestamp in (master['generated_at'], receipt['imported_at']):
        if datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValidationError('Publication timestamps must have timezones.')
    projects = master['projects']
    if not isinstance(projects, list) or not projects:
        raise ValidationError('Missing canonical records.')
    for project in projects:
        if not isinstance(project, dict) or {'_id', '_ingest'} & project.keys():
            raise ValidationError('Malformed record or reserved import fields.')
        for key in ('project_id', 'project_name', 'utility'):
            if not isinstance(project.get(key), str) or not project[key].strip():
                raise ValidationError('Missing canonical identity field.')
        if not isinstance(project.get('source_metadata'), dict):
            raise ValidationError('Missing canonical source metadata.')
        if not all(k in project for k in ('verified_geometry', 'estimated_geometry', 'analysis_geometry',
                                         'planned_start_year', 'planned_end_year', 'in_service_year')):
            raise ValidationError('Missing canonical geometry or timing fields.')
    # Reuse the application's deterministic rules, including geometry precedence,
    # nullable years, identities, saved distances, and publication policy.
    validate_publication(master, parsed['website_data.json'])
    if receipt.get('opportunity_policy') != parsed['website_data.json']['opportunity_policy']:
        raise ValidationError('Receipt policy mismatch.')
    counts = {'projects': len(projects), **Counter(p['utility'] for p in projects),
              **Counter(p['geometry_status'] for p in projects),
              **Counter(p['analysis_geometry']['type'] for p in projects if p['analysis_geometry'] is not None)}
    if counts != EXPECTED:
        raise ValidationError('Publication counts differ from the reviewed 78-project baseline; review required.')
    for field, key in (('total_projects', 'projects'), ('DESC_count', 'DESC'), ('GPC_count', 'GPC'),
                       ('verified_geometry_count', 'VERIFIED'), ('estimated_geometry_count', 'ESTIMATED'),
                       ('unresolved_count', 'UNRESOLVED')):
        if master.get(field) != counts[key] or parsed['summary_statistics.json'].get(field) != counts[key]:
            raise ValidationError('Publication summary count mismatch.')
    explorer = parsed['project_explorer.json']
    if explorer.get('total_projects') != len(projects) or len(explorer['projects']) != len(projects):
        raise ValidationError('Explorer publication is incomplete.')
    for original, reduced in zip(projects, explorer['projects']):
        if not isinstance(reduced, dict) or reduced.get('project_id') != original['project_id'] or any(original.get(k) != v for k, v in reduced.items()):
            raise ValidationError('Explorer publication does not match canonical records.')
    return master, receipt, hashes


def build_documents(publication, imported_at):
    """Build and BSON-preflight the exact documents for dry-run or transaction."""
    try:
        if not isinstance(imported_at, datetime) or imported_at.tzinfo is None:
            raise ValidationError('Import timestamp must be timezone-aware.')
        master, receipt, hashes = _validate(publication)
        dataset_id = 'sha256:' + hashes[MASTER]
        documents = []
        for index, project in enumerate(master['projects']):
            doc = deepcopy(project)
            doc['_id'] = project['project_id']
            doc['_ingest'] = {'dataset_id': dataset_id, 'source_file': 'data/published/' + MASTER,
                              'source_index': index, 'schema_version': 2, 'imported_at': imported_at}
            documents.append(doc)
        metadata = {'_id': dataset_id, 'dataset_kind': 'canonical_publication',
                    'master_sha256': hashes[MASTER], 'source_file': 'data/published/' + MASTER,
                    'dataset_version': master['dataset_version'], 'pipeline_commit': master['pipeline_commit'],
                    'generated_at': master['generated_at'],
                    'source_metadata': deepcopy({k: v for k, v in master.items() if k != 'projects'}),
                    'publication_receipt': deepcopy(receipt),
                    'receipt_sha256': sha256(publication['receipt']).hexdigest(),
                    'project_ids': [p['project_id'] for p in master['projects']],
                    'project_count': len(documents), 'schema_version': 2,
                    'imported_at': imported_at, 'status': 'complete'}
        for doc in [*documents, metadata]:
            if len(BSON.encode(doc)) > 16 * 1024 * 1024:
                raise ValidationError('Document exceeds BSON size limit.')
        return documents, metadata
    except ValidationError:
        raise
    except Exception:
        raise ValidationError('Malformed or BSON-incompatible canonical publication.') from None
