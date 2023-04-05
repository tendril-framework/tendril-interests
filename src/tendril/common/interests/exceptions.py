

from tendril.common.exceptions import HTTPCodedException


class InterestException(HTTPCodedException):
    def __init__(self, interest_id, interest_name):
        self.interest_id = interest_id
        self.interest_name = interest_name


class InterestActionException(InterestException):
    def __init__(self, action, *args, **kwargs):
        super(InterestActionException, self).__init__(*args, **kwargs)
        self.action = action


class InterestStateException(InterestActionException):
    status_code = 406

    def __init__(self, state, allowed, *args, **kwargs):
        super(InterestStateException, self).__init__(*args, **kwargs)
        self.state = state
        self.allowed = allowed

    def __str__(self):
        return f"The interest {self.interest_id}, {self.interest_name} is not in a " \
               f"state which allows '{self.action}'. This is only in allowed in " \
               f"'{self.allowed}', but it is '{self.state}'"


class AuthorizationRequiredError(InterestActionException):
    status_code = 403

    def __init__(self, user_id, *args, **kwargs):
        super(AuthorizationRequiredError, self).__init__(*args, **kwargs)
        if hasattr(user_id, 'id'):
            self.user_id = user_id.id
        else:
            self.user_id = user_id

    def __str__(self):
        return f"User {self.user_id} does not have the necessary permissions " \
               f"to execute the action '{self.action}' " \
               f"on interest {self.interest_id}, {self.interest_name}"


class ActivationError(InterestException):
    status_code = 406

    def __init__(self, *args, **kwargs):
        super(ActivationError, self).__init__(*args, **kwargs)


class ActivationNotAllowedFromState(ActivationError):
    def __init__(self, state, *args, **kwargs):
        super(ActivationNotAllowedFromState, self).__init__(*args, **kwargs)
        self.state = state

    def __str__(self):
        return f"Could not activate interest {self.interest_id}, f{self.interest_name}. " \
               f"The interest is in state {self.state} and cannot be activated."


class RequiredRoleNotPresent(ActivationError):
    def __init__(self, role, *args, **kwargs):
        super(RequiredRoleNotPresent, self).__init__(*args, **kwargs)
        self.role = role

    def __str__(self):
        return f"Could not activate interest {self.interest_id}, f{self.interest_name}. " \
               f"The interest does not have a user in a require role {self.role}."


class RequiredParentNotPresent(ActivationError):
    def __str__(self):
        return f"Could not activate interest {self.interest_id}, f{self.interest_name}. " \
               f"The interest is not linked to a parent."


class InterestCreationException(HTTPCodedException):
    status_code = 400


class TypeMismatchError(InterestCreationException):
    status_code = 406

    def __init__(self, type_name, allowed):
        self.type_name = type_name
        self.allowed = allowed

    def __str__(self):
        return f"Interest type '{self.type_name}' does not match the " \
               f"library allowed types '{self.allowed}' "


class InterestAlreadyExists(InterestCreationException):
    status_code = 409

    def __init__(self, type_name, name):
        self.type_name = type_name
        self.name = name

    def __str__(self):
        return f"Interest of type '{self.type_name}' with name '{self.name}' could not " \
               f"be created since one already exists."


class InterestNotFound(HTTPCodedException):
    status_code = 404

    def __init__(self, type_name, name, id=None):
        self.type_name = type_name
        self.name = name
        self.i_id = id

    def __str__(self):
        return f"Interest of type '{self.type_name}' with " \
               f"name '{self.name}' (id={self.i_id}) could not be found."


class InterestTypeUnsupported(HTTPCodedException):
    status_code = 406

    def __init__(self, required=None, id='<unspecified>', name='<unspecified>'):
        self.required = required
        self.i_id = id
        self.name = name

    def __str__(self):
        return f"Interest with name '{self.name}' (id={self.i_id} does not seem to be " \
               f"of a supported type for this operation. Required : {self.required}."