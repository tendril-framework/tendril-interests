

from fastapi import Request
from fastapi.responses import JSONResponse
from tendril.common.interests.exceptions import HTTPCodedException


async def generic_coded_error(request: Request, exc: HTTPCodedException):
    return JSONResponse(
        status_code=exc.status_code,
        content={'message': str(exc),
                 'exception': exc.__class__.__name__}
    )


handlers = {
    HTTPCodedException: generic_coded_error,
}
