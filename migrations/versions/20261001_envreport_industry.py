"""add environment_reports.industry -- the model's categorical confounder, asked at last

The environment instrument gained a fourth context item on 2026-10-01
(PRODUCT_DECISIONS.md §2, "Environment-instrument rulings"): which industry the
user's organization is in. `causal_graph/v1_model/solverah_model_config.yaml` has
carried `industry` as an active categorical confounder since v1, but no source
ever supplied it, so `assemble_training_data` masked it on every row and its five
level weights always came back at their prior.

Shaped like `comp` in 20260910_environment_reports:

- NULLable. Rows written before this migration were never asked and stay NULL.
  From now on, NULL is the item's "not sure / prefer not to say" option.
  `environment_reports.version` tells the two apart (env-v1-... vs env-v2-...).
- A CHECK to the config's level keys (or NULL). The keys are stored raw, the way
  `schema.sql`'s `value_cat` carries them on the company side. The model indexes
  a per-level weight by position, so an unknown key would have no weight to use.
  The vocabulary is frozen here as a literal rather than imported from `model.py`,
  because a migration describes the schema as it was on the day it ran.

REVERSIBILITY
-------------
`downgrade` drops the column, and the industry answers with it. Nothing else reads
the column yet except the training-data assembler, which falls back to masking
every row, exactly what it did before this migration.

Revision ID: 20261001_envreport_industry
Revises: 20260928_ledger_indexes
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20261001_envreport_industry"
down_revision = "20260928_ledger_indexes"
branch_labels = None
depends_on = None

INDUSTRIES = ("tech", "finance", "healthcare", "retail", "other")


def upgrade():
    op.add_column("environment_reports", sa.Column("industry", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_envreport_industry_vocab",
        "environment_reports",
        "industry IS NULL OR industry IN %s" % (INDUSTRIES,),
    )


def downgrade():
    op.drop_constraint("ck_envreport_industry_vocab", "environment_reports", type_="check")
    op.drop_column("environment_reports", "industry")
