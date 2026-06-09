"""Task status, cancel, and retry endpoints."""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pulice.api.models import TaskCancelResponse, TaskRetryResponse, TaskStatusResponse
from pulice.api.routes_stacks import _get_backend
from pulice.core.tasks import TaskStatus

router = APIRouter()


@router.get('/{task_id}', response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    backend = _get_backend()
    result = backend.get_status(task_id)
    return TaskStatusResponse(
        task_id=result.task_id,
        status=result.status.value,
        result=result.result,
        error=result.error,
        created_at=result.created_at,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )


@router.post('/{task_id}/cancel', response_model=TaskCancelResponse)
def cancel_task(task_id: str) -> TaskCancelResponse:
    backend = _get_backend()
    cancelled = backend.cancel(task_id)
    return TaskCancelResponse(task_id=task_id, cancelled=cancelled)


@router.post('/{task_id}/retry', status_code=202, response_model=TaskRetryResponse)
def retry_task(task_id: str) -> TaskRetryResponse:
    backend = _get_backend()
    old_result = backend.get_status(task_id)
    if old_result.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail='Only failed tasks can be retried.')
    try:
        new_task_id = backend.retry(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TaskRetryResponse(
        old_task_id=task_id,
        new_task_id=new_task_id,
        status=TaskStatus.PENDING.value,
    )
