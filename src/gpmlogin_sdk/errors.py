"""Public exception types. Messages are fixed text and never echo caller input or vendor text."""

from __future__ import annotations


class GPMError(Exception):
    """Base class for every error raised by this SDK.

    ``cleanup_error`` is set when a session's cleanup also failed while this error was
    propagating; the original error is never replaced.
    """

    cleanup_error: GPMCleanupError | None = None


class GPMConfigurationError(GPMError):
    """The SDK or its HTTP client is configured incorrectly."""


class GPMValidationError(GPMError):
    """A caller-supplied value was rejected before any HTTP request was made.

    ``field`` names a known contract field when one is responsible; it is never caller input.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class GPMAmbiguousMatchError(GPMError):
    """More than one entity has exactly the requested name; the SDK will not pick one."""

    def __init__(self) -> None:
        super().__init__("More than one entity matches the requested name exactly.")


class GPMOperationError(GPMError):
    """Base for errors tied to one API operation.

    ``state_uncertain`` is True when a mutating request may have been applied by GPM even though
    the SDK could not confirm it. Vendor messages and raw transport errors are intentionally not
    stored.
    """

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        status_code: int | None = None,
        state_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.state_uncertain = state_uncertain


class GPMProtocolError(GPMOperationError):
    """The response did not match the documented contract.

    ``success_confirmed`` is True only when the HTTP status was successful and the envelope said
    ``success is True`` but the ``data`` payload was malformed.
    """

    def __init__(
        self,
        operation: str,
        *,
        success_confirmed: bool = False,
        status_code: int | None = None,
        state_uncertain: bool = False,
    ) -> None:
        super().__init__(
            f"The GPM response for '{operation}' did not match the expected contract.",
            operation=operation,
            status_code=status_code,
            state_uncertain=state_uncertain,
        )
        self.success_confirmed = success_confirmed


class GPMTransportError(GPMOperationError):
    """The request could not be completed (connection or I/O failure). The cause is not kept."""

    def __init__(
        self, operation: str, *, state_uncertain: bool = False, message: str | None = None
    ) -> None:
        super().__init__(
            message
            or f"The request for '{operation}' could not be completed (connection or I/O failure).",
            operation=operation,
            state_uncertain=state_uncertain,
        )


class GPMTimeoutError(GPMTransportError):
    """The request timed out. For mutations the outcome is unknown (``state_uncertain``)."""

    def __init__(self, operation: str, *, state_uncertain: bool = False) -> None:
        super().__init__(
            operation,
            state_uncertain=state_uncertain,
            message=f"The request for '{operation}' timed out.",
        )


class GPMHTTPError(GPMOperationError):
    """GPM answered with a non-2xx HTTP status. Redirects are never followed."""

    def __init__(self, operation: str, *, status_code: int, state_uncertain: bool = False) -> None:
        super().__init__(
            f"The request for '{operation}' failed with HTTP status {status_code}.",
            operation=operation,
            status_code=status_code,
            state_uncertain=state_uncertain,
        )


class GPMAPIError(GPMOperationError):
    """GPM answered with ``success: false``. The vendor message is untrusted and not exposed."""

    def __init__(self, operation: str, *, status_code: int | None = None) -> None:
        super().__init__(
            f"GPM reported a failure for '{operation}'.",
            operation=operation,
            status_code=status_code,
            state_uncertain=False,
        )


class GPMProfileBusyError(GPMError):
    """This process already holds the profile through another exclusive session.

    The lock is in-memory and process-local. It is not distributed and does not prove whether
    the browser is running.
    """

    def __init__(self) -> None:
        super().__init__("This profile is already in use by another session in this process.")


class GPMCleanupError(GPMError):
    """Stopping the profile at the end of a session failed or did not finish in time.

    ``stop_error`` is the typed SDK error from the stop request when there was one. The browser
    may still be running; check and stop it outside the session.
    """

    def __init__(self, stop_error: GPMError | None = None) -> None:
        super().__init__(
            "The profile could not be confirmed stopped at the end of the session; "
            "the browser may still be running."
        )
        self.stop_error = stop_error


class GPMIntegrationError(GPMError):
    """An optional integration (for example Playwright) is missing or failed to connect."""
