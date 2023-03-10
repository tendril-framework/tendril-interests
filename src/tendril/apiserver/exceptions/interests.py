

from fastapi import Request
from fastapi.responses import JSONResponse

from tendril.common.interests.exceptions import ActivationError
from tendril.common.interests.exceptions import AuthorizationRequiredError
from tendril.common.interests.exceptions import HTTPCodedException


async def authorization_required_error(request: Request,
                                       exc: AuthorizationRequiredError):
    return JSONResponse(
        status_code=422,
        content={'message': str(exc),
                 'exception': exc.__class__.__name__}
    )


async def activation_error(request: Request, exc: ActivationError):
    return JSONResponse(
        status_code=428,
        content={'message': str(exc),
                 'exception': exc.__class__.__name__}
    )


async def generic_coded_error(request: Request, exc: HTTPCodedException):
    return JSONResponse(
        status_code=exc.status_code,
        content={'message': str(exc),
                 'exception': exc.__class__.__name__}
    )


handlers = {
    AuthorizationRequiredError: authorization_required_error,
    ActivationError: activation_error,
    HTTPCodedException: generic_coded_error,
}
