"""Natural-language entry points; the existing engine remains the system of record."""
from .state_resolver import create_from_text, revise_from_text

__all__ = ['create_from_text', 'revise_from_text']
