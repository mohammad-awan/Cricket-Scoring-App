
"""Add authentic cricket profile assets and venue locations.

Revision ID: 20261112_0015
Revises: 845e2be3dfb1
"""

from alembic import op
import sqlalchemy as sa


# ---------------------------------------
# ALEMBIC REVISION
# ---------------------------------------

revision = "20261112_0015"
down_revision = "845e2be3dfb1"

branch_labels = None
depends_on = None


# ---------------------------------------
# UPGRADE
# ---------------------------------------

def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column(
            "photo_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "players",
        sa.Column(
            "photo_source_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "teams",
        sa.Column(
            "logo_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "teams",
        sa.Column(
            "logo_source_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.add_column(
        "venues",
        sa.Column(
            "latitude",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "venues",
        sa.Column(
            "longitude",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "venues",
        sa.Column(
            "image_url",
            sa.String(length=2048),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_venues_latitude_valid",
        "venues",
        "latitude IS NULL OR latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_venues_longitude_valid",
        "venues",
        "longitude IS NULL OR longitude BETWEEN -180 AND 180",
    )
    op.create_check_constraint(
        "ck_venues_coordinates_pair",
        "venues",
        "(latitude IS NULL AND longitude IS NULL) "
        "OR (latitude IS NOT NULL AND longitude IS NOT NULL)",
    )


# ---------------------------------------
# DOWNGRADE
# ---------------------------------------

def downgrade() -> None:
    op.drop_constraint(
        "ck_venues_coordinates_pair",
        "venues",
        type_="check",
    )
    op.drop_constraint(
        "ck_venues_longitude_valid",
        "venues",
        type_="check",
    )
    op.drop_constraint(
        "ck_venues_latitude_valid",
        "venues",
        type_="check",
    )
    op.drop_column("venues", "image_url")
    op.drop_column("venues", "longitude")
    op.drop_column("venues", "latitude")
    op.drop_column("teams", "logo_source_url")
    op.drop_column("teams", "logo_url")
    op.drop_column("players", "photo_source_url")
    op.drop_column("players", "photo_url")
