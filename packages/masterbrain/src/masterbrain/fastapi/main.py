"""
Main file for FastAPI server.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from masterbrain.endpoints import (
    chat_qa_language_router,
    chat_qa_stt_router,
    chat_qa_vision_router,
    code_edit_router,
    field_input_router,
    paper_generation_router,
    protocol_check_router,
    protocol_debug_router,
    protocol_generation_aimd_router,
    protocol_generation_assigner_router,
    protocol_generation_model_router,
    single_protocol_file_generation_router,
)
from masterbrain.endpoints.aira.router import aira_router
from masterbrain.endpoints.code_edit.logic import shutdown_code_edit_runtime_manager
from masterbrain.fastapi.provider_health import router as provider_health_router
from masterbrain.fastapi.embeddings import router as embeddings_router
from masterbrain.fastapi.usage import install_usage_context_middleware
from masterbrain.utils.llm import llm_http_exception


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await shutdown_code_edit_runtime_manager()


app = FastAPI(lifespan=lifespan)

install_usage_context_middleware(app)

ENDPOINTS_PREFIX = "/api/endpoints"

app.include_router(provider_health_router, prefix="/api", tags=["Health"])
app.include_router(embeddings_router, prefix=ENDPOINTS_PREFIX, tags=["Embeddings"])


def _json_error_response(status_code: int, detail: object) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(AuthenticationError)
async def handle_authentication_error(_: Request, exc: AuthenticationError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(PermissionDeniedError)
async def handle_permission_denied(_: Request, exc: PermissionDeniedError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(RateLimitError)
async def handle_rate_limit(_: Request, exc: RateLimitError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(APITimeoutError)
async def handle_api_timeout(_: Request, exc: APITimeoutError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(APIConnectionError)
async def handle_api_connection(_: Request, exc: APIConnectionError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(BadRequestError)
async def handle_bad_request(_: Request, exc: BadRequestError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


@app.exception_handler(APIStatusError)
async def handle_api_status(_: Request, exc: APIStatusError) -> JSONResponse:
    http_exc = llm_http_exception(exc)
    return _json_error_response(http_exc.status_code, http_exc.detail)


# AIRA #########################################################################
app.include_router(aira_router, prefix=ENDPOINTS_PREFIX, tags=["AIRA"])


# Chat #########################################################################
app.include_router(chat_qa_language_router, prefix=ENDPOINTS_PREFIX, tags=["Chat"])
app.include_router(chat_qa_vision_router, prefix=ENDPOINTS_PREFIX, tags=["Chat"])
app.include_router(chat_qa_stt_router, prefix=ENDPOINTS_PREFIX, tags=["Chat"])
app.include_router(field_input_router, prefix=ENDPOINTS_PREFIX, tags=["Chat"])
app.include_router(code_edit_router, prefix=ENDPOINTS_PREFIX, tags=["Chat"])


# Protocol Generation ##########################################################
app.include_router(
    protocol_generation_aimd_router,
    prefix=ENDPOINTS_PREFIX,
    tags=["Protocol Generation"],
)
app.include_router(
    protocol_generation_model_router,
    prefix=ENDPOINTS_PREFIX,
    tags=["Protocol Generation"],
)
app.include_router(
    protocol_generation_assigner_router,
    prefix=ENDPOINTS_PREFIX,
    tags=["Protocol Generation"],
)
app.include_router(
    single_protocol_file_generation_router,
    prefix=ENDPOINTS_PREFIX,
    tags=["Single Protocol File Generation"],
)


# Protocol Check ###############################################################

app.include_router(
    protocol_check_router, prefix=ENDPOINTS_PREFIX, tags=["Protocol Check"]
)


# Protocol Debug ###############################################################
app.include_router(
    protocol_debug_router, prefix=ENDPOINTS_PREFIX, tags=["Protocol Debug"]
)


# Paper Generation ###############################################################
app.include_router(
    paper_generation_router, prefix=ENDPOINTS_PREFIX, tags=["Paper Generation"]
)
