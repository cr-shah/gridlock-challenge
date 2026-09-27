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
                        default=Path(__file__).resolve().parent / 'data' / 'projects.json')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate and summarize only; no MongoDB imports or connection.')
    args = parser.parse_args(argv)
    try:
        data, dataset_id = load_dataset(args.input)
        imported_at = datetime.now(timezone.utc)
        documents, metadata = build_documents(data, dataset_id, args.input.name, imported_at)
    except ValidationError as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 1
    except OSError:
        print('Cannot read the input dataset.', file=sys.stderr)
        return 1

    geometry = Counter(doc['geometry']['type'] for doc in documents)
    print('Validation passed.')
    print(f'Projects: {len(documents)}; unique IDs: {len(set(metadata["project_ids"]))}')
    print(f'Geometry: {geometry["Point"]} Point, {geometry["LineString"]} LineString')
    print('Original project fields: preserved unchanged; _id equals id.')
    print(f'Dataset _note: {"preserved in source_metadata" if "_note" in data else "not present"}')
    print(f'Dataset ID: {dataset_id}')
    if args.dry_run:
        print(f'Would upsert {len(documents)} projects and 1 dataset metadata document.')
        print('No records would be deleted. Existing matching IDs would be replaced, not duplicated.')
        print('Dry run complete: no MongoDB connection or writes.')
        return 0

    from mongo_store import StoreError, import_dataset
    try:
        import_dataset(data, dataset_id, args.input.name, imported_at)
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Imported {len(documents)} projects and dataset metadata atomically; no deletions.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
