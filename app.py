from argh import dispatch_commands, arg
from os.path import expanduser, abspath
from loguru import logger

app_logger = logger.bind(name="app")
app_logger.add(expanduser("~/.trefier/app.log"), enqueue=True)


@arg('--path', help="Path to the model to load.")
def model(path=None):
    app_logger.info("Starting app in model mode")
    from trefier.cli.model_cli import ModelCLI
    cli = ModelCLI()
    cli.run(path)


@arg('path', help="Path to the cache location.")
def database(path):
    app_logger.info("Starting app in database mode from %s" % abspath(path))
    from trefier.cli.database_cli import DatabaseCLI
    from trefier.misc import Cache
    with Cache(path, DatabaseCLI) as cache:
        def write_cache():
            try:
                app_logger.info(f'Writing cache to {abspath(cache.path) if cache.path else "<undefined>"}')
                cache.write()
                cache.data.return_result(write_cache, 0)
            except Exception as e:
                app_logger.exception("Exception thrown while writing cache to disk")
                cache.data.return_result(write_cache, 1, message=str(e))
        cache.data.run(write_cache)
        cache.write_on_exit = cache.data.changed and cache.write_on_exit

from trefier.database import db

d = db.Database()
d.add_directory('data/smglom/sets/source')
d.update()
d.print_outline()

#dispatch_commands([model, database])
