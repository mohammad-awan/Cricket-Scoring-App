"""Protect immutable tournament match rule snapshots.

Revision ID: 20261015_0014
Revises: 20261015_0013
"""

from alembic import op

revision = "20261015_0014"
down_revision = "20261015_0013"
branch_labels = None
depends_on = None


FUNCTION_NAME = "protect_locked_match_rules"
TRIGGER_NAME = "trg_protect_locked_match_rules"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION protect_locked_match_rules()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.rules_locked_at IS NOT NULL
            THEN
                IF NEW.tournament_id IS DISTINCT FROM
                        OLD.tournament_id
                   OR NEW.tournament_ruleset_id IS DISTINCT FROM
                        OLD.tournament_ruleset_id
                   OR NEW.effective_rules IS DISTINCT FROM
                        OLD.effective_rules
                   OR NEW.effective_rules_checksum IS DISTINCT FROM
                        OLD.effective_rules_checksum
                   OR NEW.rules_locked_at IS DISTINCT FROM
                        OLD.rules_locked_at
                   OR NEW.team_a_id IS DISTINCT FROM
                        OLD.team_a_id
                   OR NEW.team_b_id IS DISTINCT FROM
                        OLD.team_b_id
                   OR NEW.players_per_side IS DISTINCT FROM
                        OLD.players_per_side
                   OR NEW.minimum_players_to_start IS DISTINCT FROM
                        OLD.minimum_players_to_start
                   OR NEW.total_overs IS DISTINCT FROM
                        OLD.total_overs
                   OR NEW.balls_per_over IS DISTINCT FROM
                        OLD.balls_per_over
                   OR NEW.innings_per_team IS DISTINCT FROM
                        OLD.innings_per_team
                THEN
                    RAISE EXCEPTION
                        'Locked tournament match rules cannot change'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_protect_locked_match_rules
        BEFORE UPDATE ON matches
        FOR EACH ROW
        EXECUTE FUNCTION protect_locked_match_rules()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_protect_locked_match_rules
        ON matches
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            protect_locked_match_rules()
        """
    )