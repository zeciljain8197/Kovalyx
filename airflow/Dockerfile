# Base Airflow image + a full Spark 3.5.1 distribution (not just a JRE —
# the silver_pyspark_transform DAG task shells out to the spark-submit
# binary directly, which a JRE alone doesn't provide) + dbt (installed via
# requirements.txt's dbt-core/dbt-postgres).
#
# SPARK_VERSION must match spark-master/spark-worker's actual image
# (bitnamilegacy/spark:3.5.1, see docker-compose.yml) exactly — the
# client-deploy-mode driver running in this container talks Spark's
# internal RPC/serialization protocol directly to those executors, and
# even a patch-version mismatch (3.5.0 driver vs 3.5.1 executors, as
# this was) breaks with
# "InvalidClassException: local class incompatible" the moment any RDD
# crosses the wire.
FROM apache/airflow:2.9.3-python3.11

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

ENV SPARK_VERSION=3.5.1
ENV SPARK_HOME=/opt/spark
ENV PATH=$PATH:$SPARK_HOME/bin

RUN curl -fsSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz" \
        -o /tmp/spark.tgz \
    && mkdir -p "$SPARK_HOME" \
    && tar -xzf /tmp/spark.tgz -C "$SPARK_HOME" --strip-components=1 \
    && rm /tmp/spark.tgz \
    && chown -R airflow:root "$SPARK_HOME"

# The stock Spark hadoop3 binary distribution doesn't include hadoop-aws
# or the AWS SDK (needed for s3a:// support), so silver_pyspark_transform's
# spark-submit used to fetch them at runtime via --packages instead. That
# meant the driver (this container) resolved its own fresh copies via Ivy
# while spark-worker's image (spark/Dockerfile) already had the identical
# jars baked in — Spark ships --packages jars to executors too, so
# spark-worker ended up with two separately-classloaded copies of the same
# classes, causing an intermittent
# "NoClassDefFoundError: com/amazonaws/auth/AWSCredentialsProvider" on
# whichever s3a:// access happened to run first in a job. Baking the same
# versions in here too (matching spark/Dockerfile exactly) means driver
# and executor share identical, pre-loaded jars — no more --packages, no
# more duplicate classpath.
RUN curl -fsSL "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar" \
        -o "$SPARK_HOME/jars/hadoop-aws-3.3.4.jar" \
    && curl -fsSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar" \
        -o "$SPARK_HOME/jars/aws-java-sdk-bundle-1.12.262.jar" \
    && curl -fsSL "https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar" \
        -o "$SPARK_HOME/jars/postgresql-42.7.3.jar" \
    && chown airflow:root "$SPARK_HOME"/jars/hadoop-aws-3.3.4.jar "$SPARK_HOME"/jars/aws-java-sdk-bundle-1.12.262.jar "$SPARK_HOME"/jars/postgresql-42.7.3.jar

USER airflow

COPY requirements.txt /tmp/requirements.txt
# en_core_web_lg: same model spark/Dockerfile downloads — the Spark
# driver process for silver_pyspark_transform's client-deploy-mode
# spark-submit runs inside this container, so pii_masking.py's Presidio
# NlpEngine needs it here too.
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m spacy download en_core_web_lg
