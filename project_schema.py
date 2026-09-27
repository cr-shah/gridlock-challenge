"""Validate canonical JSON and derive documents without changing source fields."""

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path


class ValidationError(ValueError):
    """The complete input must pass validation before MongoDB is contacted."""


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Duplicate JSON object keys are not allowed.")
        result[key] = value
    return result


def _check_json(value):
    """Reject values/keys that cannot be preserved safely in BSON."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or '\x00' in key or key.startswith('$') or '.' in key:
                raise ValidationError("Unsupported document field name.")
            _check_json(item)
    elif isinstance(value, list):
        for item in value:
            _check_json(item)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("Non-finite numbers are not allowed.")
    elif isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value < 2**63:
            raise ValidationError("Integer exceeds BSON's signed 64-bit range.")
    elif value is not None and not isinstance(value, (str, bool)):
        raise ValidationError("Unsupported JSON value.")


def validate_dataset(data):
    """Validate every record, including extra provenance fields, without mutation."""
    _check_json(data)
    if not isinstance(data, dict) or not isinstance(data.get('projects'), list):
        raise ValidationError("Dataset must be an object with a projects array.")
    if not data['projects']:
        raise ValidationError("Projects array must not be empty.")
    if '_note' in data and not isinstance(data['_note'], str):
        raise ValidationError("Dataset _note must be a string.")
    seen = set()
    for index, record in enumerate(data['projects']):
        label = f"Project at index {index}"
        if not isinstance(record, dict):
            raise ValidationError(f"{label} must be an object.")
        if {'_id', 'geometry', '_ingest'} & record.keys():
            raise ValidationError(f"{label} conflicts with reserved import fields.")
        for field in ('id', 'utility', 'name', 'source_url'):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValidationError(f"{label} needs a nonempty {field} string.")
        if record['id'] in seen:
            raise ValidationError(f"{label} has a duplicate ID.")
        seen.add(record['id'])
        for field, limit in (('lat1', 90), ('lat2', 90), ('lng1', 180), ('lng2', 180)):
            value = record.get(field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not -limit <= value <= limit):
                raise ValidationError(f"{label} has missing or invalid {field}.")
        for field in ('start_year', 'end_year'):
            value = record.get(field)
            if type(value) is not int or not 1 <= value <= 9999:
                raise ValidationError(f"{label} needs an integer {field} from 1 to 9999.")
        if record['start_year'] > record['end_year']:
            raise ValidationError(f"{label} has start_year after end_year.")


def load_dataset(path):
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as exc:
        raise ValidationError("Input is not valid, unambiguous JSON.") from exc
    validate_dataset(data)
    return data, 'sha256:' + sha256(raw).hexdigest()


def build_documents(data, dataset_id, source_file, imported_at):
    validate_dataset(data)
    documents = []
    for index, record in enumerate(data['projects']):
        document = deepcopy(record)
        start = [record['lng1'], record['lat1']]
        end = [record['lng2'], record['lat2']]
        document['_id'] = record['id']
        document['geometry'] = (
            {'type': 'Point', 'coordinates': start} if start == end else
            {'type': 'LineString', 'coordinates': [start, end]}
        )
        document['_ingest'] = {
            'dataset_id': dataset_id,
            'source_file': source_file,
            'source_index': index,
            'schema_version': 1,
            'imported_at': imported_at,
        }
        documents.append(document)
    metadata = {
        '_id': dataset_id,
        'source_file': source_file,
        'source_metadata': deepcopy({k: v for k, v in data.items() if k != 'projects'}),
        'project_ids': [record['id'] for record in data['projects']],
        'project_count': len(documents),
        'schema_version': 1,
        'imported_at': imported_at,
        'status': 'complete',
    }
    return documents, metadata
