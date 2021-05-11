from enum import Enum


class ServerState(Enum):
    # This state raises InvalidRequest on other requests
    # other than `initialize` and `exit`
    UNINITIALIZED = 1
    # This state raises InvalidRequest except on `exit`
    # also `initialize` may not be called again
    INITIALIZED = 2
    # This state comes after `initialize` and `initialized` have been called,
    # the server is running and handling requests normally
    READY = 3
    # In this state the server will raise InvalidRequest and ignore notifications
    # except on `exit`
    SHUTDOWN = 4
