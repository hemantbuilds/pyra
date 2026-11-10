"""Project OS errors."""


class ProjectOSError(Exception):
    """Base error for Project OS operations."""


class NotFoundError(ProjectOSError):
    pass


class ConflictError(ProjectOSError):
    pass


class ValidationError(ProjectOSError):
    pass
