"""
Sign-up tokens: only the table model is left.

Yamabiko has no self-service sign-up; the API, the token helpers and their
emails are gone. The model stays because the table does.

Exports:
    - Models: SignUpToken (ORM model)
"""

from .models import SignUpToken as SignUpTokenModel

__all__ = [
    "SignUpTokenModel",
]
