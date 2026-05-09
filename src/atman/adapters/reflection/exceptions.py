"""
Exceptions for reflection adapters.
"""


class OllamaReflectionError(RuntimeError):
    """
    Error raised when Ollama reflection model fails after retries.

    Carries diagnostic information about the failed attempts.
    """

    def __init__(self, attempts: int, last_raw: str) -> None:
        """
        Initialize OllamaReflectionError.

        Args:
            attempts: Number of attempts made before failure
            last_raw: Raw response content from the last failed attempt
        """
        self.attempts = attempts
        self.last_raw = last_raw
        super().__init__(
            f"Ollama reflection failed after {attempts} attempts. Last raw: {last_raw[:100]}"
        )
