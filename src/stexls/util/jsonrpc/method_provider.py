from typing import Optional, Union


class MethodProvider:
    ' Interface for a provider of methods called by name and optional list or dict of parameters. '
    def is_method(self, method: str):
        ' Returns true if the method is provided by this provider. '
        raise NotImplementedError()

    async def call(self, method: str, params: Optional[Union[dict, list]] = None):
        ' Calls the method with the parameters and returns the result, awaiting it if it is a coroutine. '
        raise NotImplementedError()
