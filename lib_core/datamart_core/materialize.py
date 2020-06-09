import contextlib
import datamart_materialize
import logging
import os
import prometheus_client
import shutil
import zipfile

from datamart_core.common import hash_json
from datamart_core.fscache import cache_get_or_set

from .discovery import encode_dataset_id


logger = logging.getLogger(__name__)


PROM_DOWNLOAD = prometheus_client.Histogram(
    'download_seconds',
    "Time spent on download during materialization",
    buckets=[1.0, 10.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0,
             float('inf')],
)
PROM_CONVERT = prometheus_client.Histogram(
    'convert_seconds',
    "Time spent on conversion during materialization",
    buckets=[1.0, 10.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0, 7200.0,
             float('inf')],
)


def make_zip_recursive(zip_, src, dst=''):
    if os.path.isdir(src):
        for name in os.listdir(src):
            make_zip_recursive(
                zip_,
                os.path.join(src, name),
                dst + '/' + name if dst else name,
            )
    else:
        zip_.write(src, dst)


def dataset_cache_key(dataset_id, metadata, format, format_options):
    if format == 'csv':
        if format_options:
            raise ValueError
        materialize = metadata.get('materialize', {})
        metadata = {'id': dataset_id}
    else:
        metadata = dict(metadata, id=dataset_id)
        materialize = metadata.pop('materialize', {})
    h = hash_json({
        'format': format,
        'format_options': format_options,
        'metadata': metadata,
        'materialize': materialize,
        # Note that DATAMART_VERSION is NOT in here
        # We rely on the admin clearing the cache if required
    })
    # The hash is sufficient, other components are for convenience
    return '%s_%s.%s' % (
        encode_dataset_id(dataset_id),
        h,
        format,
    )


@contextlib.contextmanager
def get_dataset(metadata, dataset_id, format='csv', format_options=None,
                transforms=None):
    if not format:
        raise ValueError("Invalid output options")

    logger.info(
        "Getting dataset %r, size %s",
        dataset_id, metadata.get('size', 'unknown'),
    )

    # To limit the number of downloads, we always materialize the CSV file, and
    # convert it to the requested format if necessary. This avoids downloading
    # the CSV again just because we want a different format

    # Context to lock the CSV
    dataset_lock = contextlib.ExitStack()
    with dataset_lock:
        # Try to read from persistent storage
        shared = os.path.join('/datasets', encode_dataset_id(dataset_id))
        if os.path.exists(shared):
            logger.info("Reading from /datasets")
            csv_path = os.path.join(shared, 'main.csv')
        else:
            # Otherwise, materialize the CSV
            def create_csv(cache_temp):
                logger.info("Materializing CSV...")
                with PROM_DOWNLOAD.time():
                    datamart_materialize.download(
                        {'id': dataset_id, 'metadata': metadata},
                        cache_temp, None,
                        format='csv',
                        size_limit=10000000000,  # 10 GB
                    )

            csv_key = dataset_cache_key(dataset_id, metadata, 'csv', {})
            csv_path = dataset_lock.enter_context(
                cache_get_or_set(
                    '/cache/datasets', csv_key, create_csv,
                )
            )

        # Apply requested transformations
        if transforms:
            for func, descr in transforms:
                # Update metadata (which will change the cache key)
                metadata = dict(
                    metadata,
                    materialize=dict(
                        metadata['materialize'],
                        convert=(
                            metadata['materialize'].get('convert', [])
                            + [descr]
                        ),
                    )
                )

                # Update file
                def transform(cache_temp):
                    func(csv_path, cache_temp)
                transformed_key = dataset_cache_key(
                    dataset_id,
                    metadata,
                    'csv',
                    {},
                )
                with dataset_lock.pop_all():
                    csv_path = dataset_lock.enter_context(
                        cache_get_or_set(
                            '/cache/datasets',
                            transformed_key,
                            transform,
                        )
                    )

        # If CSV was requested, send it
        if format == 'csv':
            if format_options:
                raise ValueError("Invalid output options")
            yield csv_path
            return

        # Otherwise, do format conversion
        writer_cls = datamart_materialize.get_writer(format)
        if hasattr(writer_cls, 'parse_options'):
            format_options = writer_cls.parse_options(format_options)
        elif format_options:
            raise ValueError("Invalid output options")
        key = dataset_cache_key(
            dataset_id, metadata,
            format, format_options,
        )

        def create(cache_temp):
            # Do format conversion from CSV file
            logger.info("Converting CSV to %r opts=%r", format, format_options)
            with PROM_CONVERT.time():
                with open(csv_path, 'rb') as src:
                    writer = writer_cls(
                        cache_temp, format_options=format_options,
                    )
                    writer.set_metadata(dataset_id, metadata)
                    with writer.open_file('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    writer.finish()

                # Make a ZIP if it's a folder
                if os.path.isdir(cache_temp):
                    logger.info("Result is a directory, creating ZIP file")
                    zip_name = cache_temp + '.zip'
                    with zipfile.ZipFile(zip_name, 'w') as zip_:
                        make_zip_recursive(zip_, cache_temp)
                    shutil.rmtree(cache_temp)
                    os.rename(zip_name, cache_temp)

        with dataset_lock.pop_all():
            cache_path = dataset_lock.enter_context(
                cache_get_or_set(
                    '/cache/datasets', key, create,
                )
            )
        yield cache_path
