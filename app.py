from argh import dispatch_commands, arg

@arg('path', help="Path to the model to load.")
def model(path):
    from trefier.cli.model_cli import ModelCLI
    cli = ModelCLI()
    cli.run(path)

@arg('path', help="Path to the cache location.")
def database(path):
    from trefier.cli.database_cli import DatabaseCLI
    from trefier.misc import Cache
    with Cache(path, DatabaseCLI) as cache:
        @arg('path', help="Location of the cache")
        def write_cache(path):
            cache.write(path)
        def delete_cache():
            cache.delete()
        def cache_path():
            return cache.path
        cache.data.run(write_cache, delete_cache, cache_path)
        cache.write_on_exit = cache.data.changed and cache.write_on_exit

dispatch_commands([model, database])