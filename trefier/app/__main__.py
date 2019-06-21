from __future__ import annotations
from typing import Optional
from argh import arg, dispatch_commands
from os.path import expanduser, abspath
from loguru import logger


@arg('cache', help="Path to the cache location.")
@arg('--tagger', help="Path to the cache location.")
def linter(cache: str, tagger: Optional[str] = None):
    app_logger.info("Starting app in database mode from %s" % abspath(cache))
    from trefier.app.linter import LinterCLI
    from trefier.misc.Cache import Cache
    with Cache(cache, LinterCLI) as cache:
        def write_cache():
            try:
                app_logger.info(f'Writing cache to {abspath(cache.path) if cache.path else "<undefined>"}')
                cache.write()
                cache.data.return_result(write_cache, 0)
            except Exception as e:
                app_logger.exception("Exception thrown while writing cache to disk")
                cache.data.return_result(write_cache, 1, message=str(e))
        cache.data.setup()
        if tagger:
            cache.data.load_tagger(tagger)
        try:
            cache.data.run(write_cache)
        finally:
            cache.write_on_exit = cache.data.changed and cache.write_on_exit


if __name__ == '__main__':
    app_logger = logger.bind(name="app")
    app_logger.add(expanduser("~/.trefier/app.log"), enqueue=True)
    dispatch_commands([linter])
