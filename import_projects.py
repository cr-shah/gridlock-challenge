"""Import canonical projects without editing files.

    python -B import_projects.py --dry-run
    python -B import_projects.py

Actual imports require exported MONGODB_URI and MONGODB_DB; .env is not loaded.
Projects are upserted by their original ID; absent records are never deleted.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

from project_schema import ValidationError, build_documents, load_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path,
                        default=Path(__file__).resolve().parent / 'data' / 'published' / 'gridlock_master_projects.json')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate and summarize only; no MongoDB imports or connection.')
    args = parser.parse_args(argv)
    try:
        publication = load_dataset(args.input)
        imported_at = datetime.now(timezone.utc)
        documents, metadata = build_documents(publication, imported_at)
    except ValidationError as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 1
    except OSError:
        print('Cannot read the input dataset.', file=sys.stderr)
        return 1

    utilities = Counter(doc['utility'] for doc in documents)
    statuses = Counter(doc['geometry_status'] for doc in documents)
    geometry = Counter(doc['analysis_geometry']['type'] for doc in documents
                       if doc['analysis_geometry'] is not None)
    print('Publication integrity and local validation: PASS (4 artifact hashes).')
    print(f'Projects: {len(documents)}; unique canonical IDs: {len(set(metadata["project_ids"]))}')
    print(f'Utilities: {utilities["DESC"]} DESC; {utilities["GPC"]} GPC')
    print(f'Geometry status: {statuses["VERIFIED"]} VERIFIED; {statuses["ESTIMATED"]} ESTIMATED; {statuses["UNRESOLVED"]} UNRESOLVED')
    print(f'Geometry: {sum(geometry.values())} total; {geometry["Point"]} Points; {geometry["LineString"]} LineStrings; {statuses["UNRESOLVED"]} null')
    print('Canonical fields, nulls, geometry and evidence: preserved unchanged.')
    print('Identity: _id equals project_id; canonical project_id retained.')
    print('Publication metadata, ordered IDs and receipt provenance: preserved.')
    print('BSON validation: PASS for all project and dataset documents.')
    print(f'Dataset ID: {metadata["_id"]}')
    if args.dry_run:
        print(f'Would upsert {len(documents)} projects and 1 dataset metadata document.')
        print('No records would be deleted. Existing matching IDs would be replaced, not duplicated.')
        print('Dry run complete: no MongoDB connection or writes.')
        return 0

    from mongo_store import StoreError, import_dataset
    try:
        import_dataset(publication, imported_at)
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Imported {len(documents)} projects and dataset metadata atomically; no deletions.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
