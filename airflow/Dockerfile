# Base Airflow image + a full Spark 3.5.0 distribution (not just a JRE —
# the silver_pyspark_transform DAG task shells out to the spark-submit
# binary directly, which a JRE alone doesn't provide) + dbt (installed via
# requirements.txt's dbt-core/dbt-postgres).
FROM apache/airflow:2.9.3-python3.11

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

ENV SPARK_VERSION=3.5.0
ENV SPARK_HOME=/opt/spark
ENV PATH=$PATH:$SPARK_HOME/bin

RUN curl -fsSL "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop3.tgz" \
        -o /tmp/spark.tgz \
    && mkdir -p "$SPARK_HOME" \
    && tar -xzf /tmp/spark.tgz -C "$SPARK_HOME" --strip-components=1 \
    && rm /tmp/spark.tgz \
    && chown -R airflow:root "$SPARK_HOME"

USER airflow

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
