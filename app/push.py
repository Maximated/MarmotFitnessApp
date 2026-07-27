import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_user
from app.models import BlockExercise, PushSubscription, User, Workout
from app.training_urls import training_url

router = APIRouter(prefix="/push")

logger = logging.getLogger(__name__)


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.get("/public-key")
async def public_key():
    return {"key": settings.vapid_public_key}


@router.post("/subscribe")
async def subscribe(
    subscription: SubscriptionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    existing = (
        db.query(PushSubscription)
        .filter(PushSubscription.endpoint == subscription.endpoint)
        .first()
    )
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = subscription.keys.p256dh
        existing.auth = subscription.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=subscription.endpoint,
                p256dh=subscription.keys.p256dh,
                auth=subscription.keys.auth,
            )
        )
    db.commit()
    return {"ok": True}


def send_push_for_workout(db: Session, workout: Workout) -> None:
    if not workout.rest_notify_text:
        return

    subscriptions = (
        db.query(PushSubscription).filter(PushSubscription.user_id == workout.user_id).all()
    )
    if not subscriptions:
        return

    url = "/"
    if workout.active_block_exercise_id is not None:
        block_exercise = db.get(BlockExercise, workout.active_block_exercise_id)
        if block_exercise is not None:
            url = training_url(
                block_exercise.id,
                block_exercise.exercise_id,
                {"block_exercise_id": block_exercise.id},
            )

    payload = {
        "title": "Descanso terminado",
        "body": workout.rest_notify_text,
        "url": url,
    }

    for subscription in subscriptions:
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
            )
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (404, 410):
                db.delete(subscription)
            else:
                logger.warning("Web push failed for subscription %s: %s", subscription.id, exc)
