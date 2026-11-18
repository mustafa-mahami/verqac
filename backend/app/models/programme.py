"""The project's time programme: planned start and finish of every stage x location cell.

It is a record (type "programme") the contractor submits and supervision approves; each update is a new
revision. The first approved revision is the baseline, the latest approved one is the current programme."""
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base


class Programme(Base):
    __tablename__ = "programmes"

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    # [{stage_id, location_id | None, start: "YYYY-MM-DD", finish: "YYYY-MM-DD"}]
    lines: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    # floor-cycle inputs kept for editing again: [{stage_id, start, duration, lag}]
    cycles: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")  # manual | cycle | import
