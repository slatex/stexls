
class CapabilityBase:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled


class WorkDoneProgressCapability(CapabilityBase):
    def __init__(self, enabled: bool = False) -> None:
        super().__init__(enabled)
