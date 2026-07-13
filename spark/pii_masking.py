"""
Kovalyx — Silver-layer PII masking module.

Standalone PySpark-compatible module used by spark/silver_transform.py.
Applies field-level masking rules to whichever of customer_name,
customer_email, customer_phone, shipping_address are present in a given
Silver DataFrame (different tables carry different subsets — orders.csv
only has shipping_address, for example), and builds an append-only audit
trail describing what was masked without ever storing the original value.

Masking rules:
    customer_name     -> literal "MASKED_NAME"      (Presidio-backed)
    customer_email    -> SHA-256 hash, column renamed to hashed_email
                          (plain hashlib — deterministic, NOT Presidio, so
                          the same email always hashes the same way for
                          downstream joins/cohort analysis)
    customer_phone     -> literal "MASKED_PHONE"     (Presidio-backed)
    shipping_address   -> NULL (fully suppressed)
    card_last4/card_type -> passed through unchanged (not PII)

Presidio usage: customer_name/customer_phone run a real
AnalyzerEngine.analyze() + AnonymizerEngine.anonymize() pass, but the
anonymize operator's replacement value is the fixed literal either way —
these two columns are 100% known-PII by schema position, so gating the
mask on NER confidence would risk a silent leak on a detection miss.
shipping_address runs AnalyzerEngine.analyze() purely for audit richness:
the entity types Presidio finds there (LOCATION/PERSON/etc.) are folded
into the audit record's masking_action so a compliance reviewer can see
what kind of PII was actually suppressed, even though the DataFrame value
itself is unconditionally nulled either way.
"""

from __future__ import annotations

import hashlib
import logging
from functools import reduce

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

logger = logging.getLogger("kovalyx.pii_masking")

_PRESIDIO_ANALYZER: AnalyzerEngine | None = None
_PRESIDIO_ANONYMIZER: AnonymizerEngine | None = None


def _presidio_engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    """Lazily initializes Presidio once per Python worker process, not
    once per row — AnalyzerEngine construction loads a spaCy model, which
    is far too expensive to redo inside a per-row UDF call."""
    global _PRESIDIO_ANALYZER, _PRESIDIO_ANONYMIZER
    if _PRESIDIO_ANALYZER is None:
        _PRESIDIO_ANALYZER = AnalyzerEngine()
        _PRESIDIO_ANONYMIZER = AnonymizerEngine()
    return _PRESIDIO_ANALYZER, _PRESIDIO_ANONYMIZER


def _hash_email(value: str | None) -> str | None:
    """Deterministic SHA-256 hash of a normalized email address."""
    if value is None:
        return None
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _mask_name(text: str | None) -> str | None:
    """Runs Presidio detection + anonymization for PERSON entities, always
    landing on the literal "MASKED_NAME" — via the anonymizer's replace
    operator when Presidio finds a match, or a direct fallback if it
    doesn't, so a NER miss can never leave the real name in place."""
    if text is None:
        return None
    try:
        analyzer, anonymizer = _presidio_engines()
        results = analyzer.analyze(text=text, language="en", entities=["PERSON"])
        if results:
            return anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators={"PERSON": OperatorConfig("replace", {"new_value": "MASKED_NAME"})},
            ).text
    except Exception:  # noqa: BLE001
        logger.warning("Presidio analysis failed for customer_name — falling back to deterministic mask", exc_info=True)
    return "MASKED_NAME"


def _mask_phone(text: str | None) -> str | None:
    """Same Presidio-backed-with-fallback pattern as _mask_name(), scoped
    to PHONE_NUMBER entities."""
    if text is None:
        return None
    try:
        analyzer, anonymizer = _presidio_engines()
        results = analyzer.analyze(text=text, language="en", entities=["PHONE_NUMBER"])
        if results:
            return anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators={"PHONE_NUMBER": OperatorConfig("replace", {"new_value": "MASKED_PHONE"})},
            ).text
    except Exception:  # noqa: BLE001
        logger.warning("Presidio analysis failed for customer_phone — falling back to deterministic mask", exc_info=True)
    return "MASKED_PHONE"


def _describe_address_suppression(text: str | None) -> str:
    """Runs Presidio detection on the address text purely for audit
    richness (the DataFrame column itself is always set to NULL by
    mask_dataframe() regardless of this result) — folds detected entity
    types into the masking_action string so the audit trail records what
    kind of PII was actually present without ever storing the value."""
    if text is None:
        return "suppress"
    try:
        analyzer, _ = _presidio_engines()
        results = analyzer.analyze(text=text, language="en", entities=["LOCATION", "PERSON"])
        entity_types = sorted({r.entity_type for r in results})
        if entity_types:
            return f"suppress (entities: {', '.join(entity_types)})"
    except Exception:  # noqa: BLE001
        logger.warning("Presidio analysis failed for shipping_address — logging bare suppression", exc_info=True)
    return "suppress"


hash_email_udf = udf(_hash_email, StringType())
mask_name_udf = udf(_mask_name, StringType())
mask_phone_udf = udf(_mask_phone, StringType())
describe_address_suppression_udf = udf(_describe_address_suppression, StringType())

_RECORD_ID_CANDIDATES = ("event_id", "customer_id", "order_id", "product_id")


def _pick_record_id_column(columns: set[str]) -> str:
    """Picks whichever natural row identifier is present — event_id for
    streaming-event DataFrames, customer_id/order_id for batch tables."""
    for candidate in _RECORD_ID_CANDIDATES:
        if candidate in columns:
            return candidate
    raise ValueError(f"No identifiable record_id column found among {sorted(columns)} for PII audit logging")


class PresidioMasker:
    """Field-level PII masking + audit-trail builder for Silver-layer
    DataFrames. One instance per pipeline run (keyed by run_id) — call
    mask_dataframe() once per table that needs masking, then
    flush_audit_log() once at the end of the job."""

    def __init__(self, run_id: str, jdbc_url: str, jdbc_props: dict):
        """
        Args:
            run_id: pipeline_run_id stamped on every audit record.
            jdbc_url: JDBC connection string for postgres-gold, e.g.
                "jdbc:postgresql://postgres-gold:5432/kovalyx_gold".
            jdbc_props: JDBC connection properties (user, password, driver).
        """
        self.run_id = run_id
        self.jdbc_url = jdbc_url
        self.jdbc_props = jdbc_props
        # Fail fast here (spaCy model missing, etc.) instead of failing
        # deep inside a UDF on the first masked row.
        _presidio_engines()
        self._audit_frames: list[DataFrame] = []
        self._masked_count = 0

    def _accumulate_audit(self, source_df: DataFrame, record_id_col: str, field_name: str, masking_action) -> None:
        """Builds one small audit DataFrame for a single masked field,
        derived from `source_df` (the *pre-mask* DataFrame) so
        original_length reflects the real original value, and appends it
        to self._audit_frames for a single batched JDBC write later.

        Deliberately builds this as a DataFrame rather than accumulating
        raw Python dicts in a driver-side list: the masking UDFs above run
        on executors, which can't safely mutate driver-side mutable state,
        so a distributed DataFrame-per-field (unioned and written once in
        flush_audit_log()) is the correct distributed equivalent of
        "collect then batch-write."
        """
        original_col = F.col(field_name)
        masking_action_col = masking_action if not isinstance(masking_action, str) else F.lit(masking_action)
        event_id_col = F.col("event_id") if "event_id" in source_df.columns else F.lit(None).cast(StringType())

        audit_df = source_df.where(original_col.isNotNull()).select(
            F.col(record_id_col).cast(StringType()).alias("record_id"),
            event_id_col.alias("event_id"),
            F.lit(field_name).alias("field_name"),
            masking_action_col.alias("masking_action"),
            F.length(original_col).cast("int").alias("original_length"),
            F.lit(self.run_id).alias("pipeline_run_id"),
            F.current_timestamp().alias("masked_at"),
        )
        row_count = audit_df.count()
        if row_count == 0:
            return
        self._masked_count += row_count
        self._audit_frames.append(audit_df)

    def mask_dataframe(self, df: DataFrame, event_type: str) -> DataFrame:
        """Applies every applicable masking rule to `df` and returns the
        masked DataFrame. Only touches columns that actually exist in
        `df`, so the same masker instance serves the streaming-events
        DataFrame (all four PII fields) and the orders DataFrame
        (shipping_address only) without extra branching by the caller.
        """
        columns = set(df.columns)
        record_id_col = _pick_record_id_column(columns)
        result = df
        fields_masked = []

        if "customer_name" in columns:
            self._accumulate_audit(df, record_id_col, "customer_name", "replace")
            result = result.withColumn("customer_name", mask_name_udf(F.col("customer_name")))
            fields_masked.append("customer_name")

        if "customer_email" in columns:
            self._accumulate_audit(df, record_id_col, "customer_email", "sha256_hash")
            result = result.withColumn("hashed_email", hash_email_udf(F.col("customer_email"))).drop("customer_email")
            fields_masked.append("customer_email->hashed_email")

        if "customer_phone" in columns:
            self._accumulate_audit(df, record_id_col, "customer_phone", "replace")
            result = result.withColumn("customer_phone", mask_phone_udf(F.col("customer_phone")))
            fields_masked.append("customer_phone")

        if "shipping_address" in columns:
            self._accumulate_audit(df, record_id_col, "shipping_address", describe_address_suppression_udf(F.col("shipping_address")))
            result = result.withColumn("shipping_address", F.lit(None).cast(StringType()))
            fields_masked.append("shipping_address")

        logger.info("mask_dataframe(event_type=%s): masked fields %s", event_type, fields_masked or "<none present>")
        return result

    def flush_audit_log(self, spark: SparkSession) -> None:
        """Unions every accumulated per-field audit DataFrame and writes
        them to audit.kovalyx_pii_audit_log in a single batched JDBC
        append — never row-by-row."""
        if not self._audit_frames:
            logger.info("No PII audit records to flush for run_id=%s", self.run_id)
            return
        combined = reduce(lambda left, right: left.unionByName(right), self._audit_frames)
        combined.write.jdbc(url=self.jdbc_url, table="audit.kovalyx_pii_audit_log", mode="append", properties=self.jdbc_props)
        logger.info("Flushed %d PII audit record(s) to audit.kovalyx_pii_audit_log (run_id=%s)", self._masked_count, self.run_id)
        self._audit_frames = []

    def get_masked_count(self) -> int:
        """Running total of PII values masked across every mask_dataframe()
        call so far, for the pipeline_audit_log.pii_events_masked metric."""
        return self._masked_count
