import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_user
from app.models import BlockExercise, PushSubscription, User, Workout
from app.training_urls import training_url
from app.workout_substitutions import get_substitution_map

router = APIRouter(prefix="/push")

logger = logging.getLogger(__name__)


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class AckRestNotifyIn(BaseModel):
    rest_until: datetime


class UnsubscribeIn(BaseModel):
    endpoint: str


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


@router.post("/unsubscribe")
async def unsubscribe(
    payload: UnsubscribeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """The profile screen's notifications toggle, switched off -- removes
    this device's subscription so the poll-based senders (rest_push_poller,
    inactivity_poller) stop reaching it. Scoped to the current user so one
    account can never delete another's subscription by guessing an
    endpoint."""
    db.query(PushSubscription).filter(
        PushSubscription.user_id == user.id, PushSubscription.endpoint == payload.endpoint
    ).delete()
    db.commit()
    return {"ok": True}


@router.post("/ack-rest-notify")
async def ack_rest_notify(
    ack: AckRestNotifyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Called right when the client shows the instant local notification for
    a rest deadline, so rest_push_poller (app/main.py) finds the row already
    marked and skips sending a duplicate Web Push for the same deadline a
    few seconds later. Matches on rest_until so a stale/late call can never
    suppress the push for a newer rest period that's already replaced it."""
    workout = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.rest_until == ack.rest_until,
            Workout.rest_push_sent_at.is_(None),
        )
        .first()
    )
    if workout is not None:
        workout.rest_push_sent_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


def send_push_for_workout(db: Session, workout: Workout) -> None:
    if not workout.rest_notify_text:
        return

    # `next` always gets a real destination (never left unset) -- omitting
    # it is exactly what made the "<<" button on the screen this
    # notification opens fall back to /exercises (the general catalog)
    # instead of back to today's day. The pin, unlike `next`, doesn't need
    # threading through here at all: it's persisted on the Workout itself
    # (see render_training_log), so the page picks it up regardless of
    # what URL brought the user there.
    url = f"/programs/{workout.program_id}/today" if workout.program_id is not None else "/"
    if workout.active_block_exercise_id is not None:
        block_exercise = db.get(BlockExercise, workout.active_block_exercise_id)
        if block_exercise is not None:
            substitution_map = get_substitution_map(db, workout.id)
            effective_exercise_id = substitution_map.get(block_exercise.id, block_exercise.exercise_id)
            params = {"block_exercise_id": block_exercise.id, "next": url}
            url = training_url(block_exercise.id, effective_exercise_id, params)

    _send_push(db, workout.user_id, "Descanso terminado", workout.rest_notify_text, url)


def send_inactivity_prompt_push(db: Session, workout: Workout) -> None:
    url = f"/programs/{workout.program_id}/today" if workout.program_id is not None else "/"
    _send_push(
        db,
        workout.user_id,
        "¿Sigues entrenando?",
        "Llevas media hora sin apuntar nada. Si no respondes, el entrenamiento se dará por finalizado en 5 minutos.",
        url,
    )


def _send_push(db: Session, user_id: int, title: str, body: str, url: str) -> None:
    subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not subscriptions:
        return

    payload = {"title": title, "body": body, "url": url}

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
        except Exception:
            # Anything below the HTTP layer (connection errors, timeouts,
            # DNS failures) never becomes a WebPushException -- it must not
            # abort the loop, or a retry of this whole function on the next
            # poll would re-send to every subscription that already
            # succeeded just above.
            logger.warning("Web push request failed for subscription %s", subscription.id, exc_info=True)
