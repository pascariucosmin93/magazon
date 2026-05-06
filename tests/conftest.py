import os

# Provide required settings so pydantic-settings validation passes during tests.
# These are never used against a real database or Redis in unit tests.
os.environ.setdefault("POSTGRES_PASSWORD", "test-password-for-unit-tests")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minimum-32-chars-xxx")
