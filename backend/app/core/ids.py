import secrets


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


class SequentialIds:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}_{self.n:012d}"
