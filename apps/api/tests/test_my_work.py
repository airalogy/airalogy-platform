"""The personal queue follows the existing task, action and approval identities."""

import asyncio
import os
from datetime import UTC, datetime

import pytest
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchRun,
    ResearchTask,
)
from app.routers.my_work import my_work

from tests.test_record_analysis_postgres import database, seed_analysis


@pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)
def test_research_work_queue_with_live_assignment_and_deadline():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                task = ResearchTask(
                    lab_id=seed.lab.id,
                    project_id=seed.project.id,
                    title="Review deliverable",
                    status="review_required",
                    goal="Synthetic",
                    owner_user_id=seed.owner.id,
                    created_by_user_id=seed.owner.id,
                )
                db.add(task)
                await db.flush()
                execution = ResearchRun(
                    task_id=task.id, run_number=1, requested_by_user_id=seed.owner.id
                )
                db.add(execution)
                await db.flush()
                action = ResearchAction(
                    run_id=execution.id,
                    sequence=1,
                    plan_version=1,
                    kind="human_work_item",
                    title="Check deliverable",
                    executor_type="human",
                    preview_digest="test",
                    idempotency_key="test",
                    input_data={"private_payload": "never include this"},
                )
                db.add(action)
                await db.flush()
                item = ResearchHumanWorkItem(
                    action_id=action.id,
                    assignee_user_id=seed.recorder.id,
                    due_at=datetime(2020, 1, 1, 21, tzinfo=UTC),
                )
                approval = ResearchApproval(
                    action_id=action.id,
                    approver_user_id=seed.owner.id,
                    requested_by_user_id=seed.owner.id,
                    preview_digest="test",
                )
                db.add_all([item, approval])
                await db.flush()

                async def queue(user, scope="mine"):
                    return (
                        await my_work(
                            user,
                            db,
                            view="todos",
                            scope=scope,
                            project_id=seed.project.id,
                            time_zone="Asia/Shanghai",
                            page=1,
                            page_size=20,
                        )
                    )["items"]

                assert {r["id"] for r in await queue(seed.owner)} == {
                    task.id,
                    approval.id,
                }
                assigned = await queue(seed.recorder)
                assert len(assigned) == 1 and assigned[0]["id"] == item.id
                assert assigned[0]["due"].isoformat() == "2020-01-02"
                all_work = await queue(seed.owner, "visible")
                assert all_work[0]["id"] == item.id and len(all_work) == 3
                assert "private_payload" not in str(all_work)
                assert await queue(seed.outsider, "visible") == []
                item.status = "accepted"
                approval.status = "approved"
                await db.flush()
                assert [r["id"] for r in await queue(seed.owner, "visible")] == [
                    task.id
                ]

    asyncio.run(run())
