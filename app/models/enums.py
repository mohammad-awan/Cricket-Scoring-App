from __future__ import annotations
from enum import Enum
from typing import TypeVar
from sqlalchemy import Enum as SQLAlchemyEnum


EnumT = TypeVar("EnumT", bound=Enum)


class TeamStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PlayerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class VenueStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TournamentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MatchType(str, Enum):
    T20 = "t20"
    ODI = "odi"
    TEST = "test"
    OTHER = "other"


class MatchStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    LIVE = "live"
    INNINGS_BREAK = "innings_break"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TossDecision(str, Enum):
    BAT = "bat"
    BOWL = "bowl"


class PlayerRole(str, Enum):
    BATTER = "batter"
    BOWLER = "bowler"
    ALL_ROUNDER = "all_rounder"
    WICKET_KEEPER = "wicket_keeper"


class InningsStatus(str, Enum):
    PENDING = "pending"
    LIVE = "live"
    BREAK = "break"
    COMPLETED = "completed"


class WicketType(str, Enum):
    BOWLED = "bowled"
    CAUGHT = "caught"
    LBW = "lbw"
    RUN_OUT = "run_out"
    STUMPED = "stumped"
    HIT_WICKET = "hit_wicket"
    OBSTRUCTING_FIELD = "obstructing_field"


class DeliveryStatus(str, Enum):
    RECORDED = "recorded"
    VOID = "void"


class CorrectionType(str, Enum):
    VOID = "void"
    AMENDMENT = "amendment"


class AuditAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    ARCHIVED = "archived"
    RESTORED = "restored"
    CORRECTED = "corrected"


class BattingHand(str, Enum):
    RIGHT = "right"
    LEFT = "left"


class BowlingArm(str, Enum):
    RIGHT = "right"
    LEFT = "left"
    NONE = "none"


class BowlingStyle(str, Enum):
    FAST = "fast"
    FAST_MEDIUM = "fast_medium"
    MEDIUM_FAST = "medium_fast"
    MEDIUM = "medium"
    OFF_BREAK = "off_break"
    LEG_BREAK = "leg_break"
    ORTHODOX = "orthodox"
    WRIST_SPIN = "wrist_spin"
    MYSTERY_SPIN = "mystery_spin"
    OTHER = "other"



def enum_values(enum_class: type[EnumT]) -> list[str]:
    return [member.value for member in enum_class]



def db_enum(enum_class: type[EnumT], name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum_class,
        name=name,
        values_callable=enum_values,
        native_enum=True,
        validate_strings=True,
    )



