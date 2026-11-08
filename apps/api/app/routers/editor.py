import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.database import DBSession
from app.libs.masterbrain import (
    protocol_check,
    protocol_code_edit,
    protocol_debug,
    protocol_generate_aimd,
    protocol_generate_assigner,
    protocol_generate_model,
)
from app.models.chat import Chat, ChatModel, ChatType
from app.routers.chats.file_processor import trim_content
from app.routers.chats.utils import check_model_usage
from app.routers.depends import CurrentUser
from app.services.model_usage import create_usage_context
from app.services.protocol_authoring import (
    MAX_SOURCE_CHARS,
    SourceFile,
    SourceValidation,
    SourceWorkspace,
    syntax_repair_prompt,
    validate_edit_result,
    validate_sources,
)

router = APIRouter(
    prefix="/editor",
    tags=["editor"],
    # dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

MAX_PROTOCOL_INSTRUCTION_CHARS = 20000
MAX_PROTOCOL_INSTRUCTION_TOKENS = MAX_PROTOCOL_INSTRUCTION_CHARS // 4
TEXT_FILE_EXTENSIONS = {".txt", ".md", ".markdown"}
DOCUMENT_FILE_EXTENSIONS = {".pdf", ".doc", ".docx"}


class ProtocolInstructionExtractionResponse(BaseModel):
    filename: str
    text: str
    was_trimmed: bool = False
    content_type: str


def _decode_text_content(raw_content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Unable to decode the uploaded text file. Please use UTF-8, UTF-8 with BOM, or GB18030 encoding.",
    )


async def _extract_protocol_instruction_text(
    file: UploadFile,
) -> ProtocolInstructionExtractionResponse:
    from markitdown import MarkItDown

    filename = file.filename or "uploaded-file"
    suffix = Path(filename).suffix.lower()
    content_type = file.content_type or "application/octet-stream"

    if suffix not in TEXT_FILE_EXTENSIONS | DOCUMENT_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only .txt, .md, .pdf, .doc, and .docx files are supported.",
        )

    raw_content = await file.read()
    if not raw_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if suffix in TEXT_FILE_EXTENSIONS:
        content = _decode_text_content(raw_content)
    else:
        tmp_file_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(raw_content)
                tmp_file_path = tmp_file.name

            result = MarkItDown().convert(tmp_file_path)
            content = result.text_content
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to extract text from {filename}. Please try a standard PDF or Word file.",
            ) from exc
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)

    content = content.strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail=f"No readable text was found in {filename}.",
        )

    trimmed_content, was_trimmed = trim_content(
        content,
        max_tokens=MAX_PROTOCOL_INSTRUCTION_TOKENS,
    )
    return ProtocolInstructionExtractionResponse(
        filename=filename,
        text=trimmed_content,
        was_trimmed=was_trimmed,
        content_type=content_type,
    )


@router.post("/syntax_check")
async def syntax_check(
    _: CurrentUser,
    file_type: Annotated[Literal["python", "aimd"], Body(embed=True)],
    file_content: Annotated[str, Body(embed=True, max_length=MAX_SOURCE_CHARS)],
):
    report = await asyncio.to_thread(
        validate_sources,
        [
            SourceFile(
                path="source.py" if file_type == "python" else "protocol.aimd",
                content=file_content,
            )
        ],
    )
    first = report.diagnostics[0] if report.diagnostics else None
    return {
        **report.model_dump(),
        "result": report.status == "valid",
        "message": first.message if first else "",
        "lineno": first.line if first else 0,
        "offset": first.column if first else 0,
        "errors": [
            {"message": d.message, "start_line": d.line, "start_col": d.column}
            for d in report.diagnostics
        ],
    }


@router.post("/validate_sources")
async def check_protocol_sources(
    _: CurrentUser, params: SourceWorkspace
) -> SourceValidation:
    return await asyncio.to_thread(validate_sources, params.files)


class GeneratedProtocolDraft(BaseModel):
    content: str
    original_content: str
    validation: SourceValidation
    repair_status: Literal[
        "not_needed", "applied", "needs_review", "failed", "unavailable"
    ]


@router.post("/protocol_generate_draft")
async def generate_protocol_draft(
    db_session: DBSession,
    current_user: CurrentUser,
    instruction: Annotated[
        str, Body(embed=True, min_length=1, max_length=MAX_PROTOCOL_INSTRUCTION_CHARS)
    ],
    model: Annotated[ChatModel, Body(embed=True)],
) -> GeneratedProtocolDraft:
    await check_model_usage(db_session, current_user, model)
    chat = Chat(
        user_id=current_user.id,
        context={"instruction": instruction},
        messages=[],
        type=ChatType.PROTOCOL_GENERATE,
        model=model.model_dump(),
        model_type=model.model_type.value,
    )
    usage = create_usage_context(
        feature="editor.protocol_generate_aimd", user_id=current_user.id
    )
    content = ""
    async for chunk in protocol_generate_aimd(chat, usage_context=usage):
        content += chunk
        if len(content) > MAX_SOURCE_CHARS:
            raise HTTPException(
                413,
                "Generated Protocol exceeds the source limit. Please request a smaller Protocol.",
            )
    original = content
    files = [SourceFile(path="protocol.aimd", content=content, type="aimd")]
    report = await asyncio.to_thread(validate_sources, files)
    repair_status = "not_needed"
    if report.status == "invalid":
        # One repair attempt only; retain the generated source on every failure.
        repair_status = "failed"
        try:
            await check_model_usage(db_session, current_user, model)
            result = await protocol_code_edit(
                {
                    "model": model.model_dump(),
                    "prompt": syntax_repair_prompt(report),
                    "workspace_id": f"user:{current_user.id}:generated:{uuid4()}",
                    "files": [file.model_dump() for file in files],
                    "active_file_path": "protocol.aimd",
                },
                usage_context=create_usage_context(
                    feature="editor.protocol_syntax_repair", user_id=current_user.id
                ),
            )
            result = validate_edit_result(result, files)
            changes = result.get("changed_files", [])
            repair_status = "needs_review"
            if (
                len(changes) == 1
                and changes[0]["path"] == "protocol.aimd"
                and changes[0]["status"] == "modified"
                and changes[0]["content"].strip()
                and not result.get("warnings")
                and result.get("risk", {}).get("level") == "safe"
                and result.get("risk", {}).get("recommended_action") == "auto_apply"
            ):
                candidate = SourceFile(
                    path="protocol.aimd", content=changes[0]["content"], type="aimd"
                )
                checked = await asyncio.to_thread(validate_sources, [candidate])
                if checked.status == "valid":
                    content, report, repair_status = (
                        candidate.content,
                        checked,
                        "applied",
                    )
        except Exception:
            # Quota, model or repair-runtime failures must not discard the draft.
            logger.exception("Generated Protocol syntax repair failed; original retained")
            repair_status = "failed"
    elif report.status == "unavailable":
        repair_status = "unavailable"
    chat.messages.append({"role": "assistant", "content": original})
    if content != original:
        chat.messages.append({"role": "assistant", "content": content})
    chat.context = {
        **chat.context,
        "validation": report.model_dump(),
        "repair_status": repair_status,
    }
    db_session.add(chat)
    await db_session.commit()
    return GeneratedProtocolDraft(
        content=content,
        original_content=original,
        validation=report,
        repair_status=repair_status,
    )


@router.post("/protocol_instruction_extract")
async def extract_protocol_instruction_file(
    _: CurrentUser,
    file: Annotated[UploadFile, File(...)],
) -> ProtocolInstructionExtractionResponse:
    return await _extract_protocol_instruction_text(file)


@router.post("/protocol_generate_aimd", response_class=PlainTextResponse)
async def generate_protocol_aimd(
    db_session: DBSession,
    current_user: CurrentUser,
    instruction: Annotated[
        str,
        Body(embed=True, min_length=1, max_length=MAX_PROTOCOL_INSTRUCTION_CHARS),
    ],
    model: Annotated[ChatModel, Body(embed=True)],
) -> StreamingResponse:
    await check_model_usage(db_session, current_user, model)

    chat = Chat(
        user_id=current_user.id,
        context={"instruction": instruction},
        messages=[],
        type=ChatType.PROTOCOL_GENERATE,
        model=model.model_dump(),
        model_type=model.model_type.value,
    )
    usage_context = create_usage_context(
        feature="editor.protocol_generate_aimd",
        user_id=current_user.id,
    )

    async def capture_and_forward_stream():
        full_response = ""
        async for chunk in protocol_generate_aimd(chat, usage_context=usage_context):
            full_response += chunk
            yield chunk

        chat.messages.append({"role": "assistant", "content": full_response})
        db_session.add(chat)
        await db_session.commit()

    return StreamingResponse(
        capture_and_forward_stream(),
        media_type="text/plain",
    )


@router.post("/protocol_generate_model", response_class=PlainTextResponse)
async def generate_protocol_model(
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_aimd: Annotated[str, Body(embed=True, min_length=1, max_length=3000)],
    model: Annotated[ChatModel, Body(embed=True)],
) -> StreamingResponse:
    await check_model_usage(db_session, current_user, model)

    chat = Chat(
        user_id=current_user.id,
        context={"protocol_aimd": protocol_aimd},
        messages=[],
        type=ChatType.PROTOCOL_GENERATE,
        model=model.model_dump(),
        model_type=model.model_type.value,
    )
    usage_context = create_usage_context(
        feature="editor.protocol_generate_model",
        user_id=current_user.id,
    )

    async def capture_and_forward_stream():
        full_response = ""
        async for chunk in protocol_generate_model(chat, usage_context=usage_context):
            full_response += chunk
            yield chunk

        chat.messages.append({"role": "assistant", "content": full_response})
        db_session.add(chat)
        await db_session.commit()

    return StreamingResponse(
        capture_and_forward_stream(),
        media_type="text/plain",
    )


@router.post("/protocol_generate_assigner", response_class=PlainTextResponse)
async def generate_protocol_assigner(
    db_session: DBSession,
    current_user: CurrentUser,
    protocol_aimd: Annotated[str, Body(embed=True, min_length=1, max_length=3000)],
    protocol_model: Annotated[str, Body(embed=True, min_length=1, max_length=3000)],
    model: Annotated[ChatModel, Body(embed=True)],
) -> StreamingResponse:
    await check_model_usage(db_session, current_user, model)

    chat = Chat(
        user_id=current_user.id,
        context={"protocol_aimd": protocol_aimd, "protocol_model": protocol_model},
        messages=[],
        type=ChatType.PROTOCOL_GENERATE,
        model=model.model_dump(),
        model_type=model.model_type.value,
    )
    usage_context = create_usage_context(
        feature="editor.protocol_generate_assigner",
        user_id=current_user.id,
    )

    async def capture_and_forward_stream():
        full_response = ""
        async for chunk in protocol_generate_assigner(
            chat, usage_context=usage_context
        ):
            full_response += chunk
            yield chunk

        chat.messages.append({"role": "assistant", "content": full_response})
        db_session.add(chat)
        await db_session.commit()

    return StreamingResponse(
        capture_and_forward_stream(),
        media_type="text/plain",
    )


class ProtocolCheckParams(BaseModel):
    feedback: str
    aimd_protocol: str | None = None
    py_model: str | None = None
    py_assigner: str | None = None
    target_file: Literal["protocol", "assigner", "model"] = "protocol"
    check_num: int = 0
    model: ChatModel


@router.post("/protocol_check", response_class=PlainTextResponse)
async def check_protocol(
    db_session: DBSession,
    current_user: CurrentUser,
    params: ProtocolCheckParams,
) -> StreamingResponse:
    await check_model_usage(db_session, current_user, params.model)

    chat = Chat(
        user_id=current_user.id,
        context={
            "feedback": params.feedback,
            "aimd_protocol": params.aimd_protocol,
            "py_model": params.py_model,
            "py_assigner": params.py_assigner,
            "target_file": params.target_file,
            "check_num": params.check_num,
        },
        messages=[],
        type=ChatType.PROTOCOL_CHECK,
        model=params.model.model_dump(),
        model_type=params.model.model_type.value,
    )
    usage_context = create_usage_context(
        feature="editor.protocol_check",
        user_id=current_user.id,
    )

    async def capture_and_forward_stream():
        full_response = ""
        async for chunk in protocol_check(chat, usage_context=usage_context):
            full_response += chunk
            yield chunk

        chat.messages.append({"role": "assistant", "content": full_response})
        db_session.add(chat)
        await db_session.commit()

    return StreamingResponse(
        capture_and_forward_stream(),
        media_type="text/plain",
    )


class ProtocolDebugParams(BaseModel):
    """Protocol debug input data"""

    full_protocol: str = Field(description="Complete AIMD protocol document")
    suspect_protocol: str = Field(
        description="Protocol segment that may contain syntax errors"
    )
    model: ChatModel


@router.post("/protocol_debug")
async def debug_protocol_content(
    db_session: DBSession,
    current_user: CurrentUser,
    params: ProtocolDebugParams,
):
    await check_model_usage(db_session, current_user, params.model)

    chat = Chat(
        user_id=current_user.id,
        context={
            "full_protocol": params.full_protocol,
            "suspect_protocol": params.suspect_protocol,
        },
        messages=[],
        type=ChatType.PROTOCOL_DEBUG,
        model=params.model.model_dump(),
        model_type=params.model.model_type.value,
    )
    usage_context = create_usage_context(
        feature="editor.protocol_debug",
        user_id=current_user.id,
    )

    response = await protocol_debug(chat, usage_context=usage_context)

    chat.messages.append({"role": "assistant", "content": response["response"]})
    db_session.add(chat)
    await db_session.commit()
    return response


class CodeEditSelection(BaseModel):
    text: str
    start_offset: int
    end_offset: int


class CodeEditHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CodeEditParams(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    workspace_id: str | None = Field(default=None, max_length=240)
    files: list[SourceFile] = Field(default_factory=list, max_length=50)
    active_file_path: str | None = None
    selection: CodeEditSelection | None = None
    chat_history: list[CodeEditHistoryMessage] = Field(default_factory=list)
    model: ChatModel
    syntax_repair: bool = False

    @model_validator(mode="after")
    def validate_workspace(self):
        if self.files:
            SourceWorkspace(files=self.files)
        return self


@router.post("/code_edit")
async def code_edit_protocol(
    db_session: DBSession,
    current_user: CurrentUser,
    params: CodeEditParams,
):
    await check_model_usage(db_session, current_user, params.model)
    payload = params.model_dump(exclude={"syntax_repair"})
    if params.syntax_repair:
        report = await asyncio.to_thread(validate_sources, params.files)
        if report.status != "invalid":
            raise HTTPException(
                409, "Check the current source before requesting a syntax repair."
            )
        payload["prompt"] = syntax_repair_prompt(report)
    workspace_suffix = params.workspace_id or "default"
    payload["workspace_id"] = f"user:{current_user.id}:editor:{workspace_suffix}"

    usage_context = create_usage_context(
        feature="editor.code_edit",
        user_id=current_user.id,
    )
    result = await protocol_code_edit(payload, usage_context=usage_context)
    return await asyncio.to_thread(
        validate_edit_result, result, params.files, require_review=params.syntax_repair
    )
