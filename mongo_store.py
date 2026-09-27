"""Atomic persistence in projects/datasets; MongoDB configuration is env-only.

Requires Atlas or another replica set / sharded deployment with transactions.
No deletion, collection dropping, or fallback to non-transactional writes.
Dataset metadata records imports, not immutable historical project snapshots.
"""

import os


class StoreError(RuntimeError):
    pass


def import_dataset(publication, imported_at):
    # Validate and prepare the entire dataset before connecting or writing.
    from project_schema import build_documents
    documents, metadata = build_documents(publication, imported_at)
    uri = os.environ.get('MONGODB_URI', '')
    database_name = os.environ.get('MONGODB_DB', '')
    if not uri.strip() or not database_name.strip():
        raise StoreError('Set both MONGODB_URI and MONGODB_DB environment variables.')
    try:
        from pymongo import MongoClient, ReplaceOne
        from pymongo.read_concern import ReadConcern
        from pymongo.write_concern import WriteConcern
    except ImportError:
        raise StoreError('Install dependencies with: python -m pip install -r requirements.txt') from None

    try:
        with MongoClient(uri, serverSelectionTimeoutMS=10000) as client:
            database = client[database_name]

            def persist(session):
                database.projects.bulk_write(
                    [ReplaceOne({'_id': doc['_id']}, doc, upsert=True) for doc in documents],
                    ordered=True, session=session,
                )
                database.datasets.replace_one(
                    {'_id': metadata['_id']}, metadata, upsert=True, session=session,
                )

            with client.start_session() as session:
                session.with_transaction(
                    persist, read_concern=ReadConcern('snapshot'),
                    write_concern=WriteConcern('majority'),
                )
    except StoreError:
        raise
    except Exception:
        # Driver errors may contain connection details; never echo them or the URI.
        raise StoreError(
            'MongoDB import could not be confirmed. Check configuration, connectivity, '
            'permissions and transaction support. No non-transactional writes were attempted. '
            'Retrying this import is safe.'
        ) from None
