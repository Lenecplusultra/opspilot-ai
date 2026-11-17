from enum import IntEnum


class Role(IntEnum):
    """Ordered roles: a higher role can do everything a lower role can."""

    VIEWER = 1
    ENGINEER = 2
    SRE = 3  # on-call / site reliability
    ADMIN = 4

    @classmethod
    def parse(cls, value: str) -> "Role":
        return cls[value.upper()]


def has_role(user_role: str, minimum: Role) -> bool:
    return Role.parse(user_role) >= minimum
