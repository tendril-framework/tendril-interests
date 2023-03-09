

class InterestException(Exception):
    def __init__(self, interest_id, interest_name):
        self.interest_id = interest_id
        self.interest_name = interest_name


class InterestActionException(InterestException):
    def __init__(self, action, *args, **kwargs):
        super(InterestActionException, self).__init__(*args, **kwargs)
        self.action = action


class AuthorizationRequiredError(InterestActionException):
    def __init__(self, user_id, *args, **kwargs):
        super(AuthorizationRequiredError, self).__init__(*args, **kwargs)
        self.user_id = user_id

    def __str__(self):
        return f"User {self.user_id} does not have the necessary permissions " \
               f"to execute the action '{self.action}' " \
               f"on interest {self.interest_id}, f{self.interest_name}"


class ActivationError(InterestException):
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
