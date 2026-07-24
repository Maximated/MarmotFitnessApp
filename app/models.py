from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    target_muscle: Mapped[str] = mapped_column(String)
    equipment: Mapped[str] = mapped_column(String)
    gif_url: Mapped[str] = mapped_column(String)
    instructions: Mapped[str] = mapped_column(Text)


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL"), index=True
    )
    day_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("day_templates.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rest_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rest_total_seconds: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(
        ForeignKey("workouts.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id"), index=True
    )
    weight: Mapped[float | None] = mapped_column(Float)
    reps: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    time: Mapped[time] = mapped_column(Time)
    comment: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    cycle_days: Mapped[int] = mapped_column(Integer)
    current_day_number: Mapped[int | None] = mapped_column(Integer)
    next_due_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class DayTemplate(Base):
    __tablename__ = "day_templates"
    __table_args__ = (
        UniqueConstraint("program_id", "day_number", name="uq_day_templates_program_id_day_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subtitle: Mapped[str | None] = mapped_column(String)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    day_number: Mapped[int] = mapped_column(Integer)


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    day_template_id: Mapped[int] = mapped_column(
        ForeignKey("day_templates.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String)
    muscle_group: Mapped[str | None] = mapped_column(String)
    variant: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    num_exercises: Mapped[int] = mapped_column(Integer)
    num_sets: Mapped[int | None] = mapped_column(Integer)
    rest_seconds: Mapped[int] = mapped_column(Integer)


class BlockExercise(Base):
    __tablename__ = "block_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(
        ForeignKey("blocks.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id"), index=True)
    pending_name: Mapped[str | None] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)
    modo_registro: Mapped[str] = mapped_column(String, default="series")
    reps_min: Mapped[int | None] = mapped_column(Integer)
    reps_max: Mapped[int | None] = mapped_column(Integer)
    duracion_segundos: Mapped[int | None] = mapped_column(Integer)
    target_weight: Mapped[float | None] = mapped_column(Float)
    is_superset_with_next: Mapped[bool] = mapped_column(Boolean, default=False)


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String, unique=True, index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
