

class AuthorizationRequiredError(PermissionError):
    pass


class ActivationError(AttributeError):
    pass


class ActivationNotAllowedFromState(ActivationError):
    pass


class RequiredRoleNotPresent(ActivationError):
    pass


class RequiredParentNotPresent(ActivationError):
    pass


class ActivationNotAllowedByUser(ActivationError, AuthorizationRequiredError):
    pass


