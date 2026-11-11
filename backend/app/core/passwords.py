"""Password strength rules for Owner-issued initial passwords and first-login changes.

Mirrors the frontend rules (frontend/src/schemas/auth.ts). Supabase Auth applies its own policy on top.
Passwords are never logged or stored by this application; they only pass through to Supabase Auth.
"""

MIN_LENGTH = 10
MAX_LENGTH = 72  # bcrypt's input limit


def validate_new_password(password: str, email: str | None = None) -> None:
    """Raises ValueError (a pydantic validation message) when the password is too weak. Never echoes it."""
    if len(password) < MIN_LENGTH:
        raise ValueError(f"Use at least {MIN_LENGTH} characters")
    if len(password.encode()) > MAX_LENGTH:
        raise ValueError(f"Use at most {MAX_LENGTH} characters")
    if not any(c.islower() for c in password) or not any(c.isupper() for c in password):
        raise ValueError("Include upper and lower case letters")
    if not any(c.isdigit() for c in password):
        raise ValueError("Include at least one number")
    if password != password.strip():
        raise ValueError("Must not start or end with a space")
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in password.lower():
            raise ValueError("Must not contain the email address")
