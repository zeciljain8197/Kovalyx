# Layers PII-masking/Silver-transform Python deps + the S3A/JDBC JARs
# onto the exact same base image docker-compose.yml's spark-master/
# spark-worker actually run (bitnamilegacy/spark:3.5.1) — this file
# previously targeted a different, unrelated base (apache/spark:3.5.0)
# and was never wired into docker-compose.yml's spark-master/
# spark-worker services at all (they used `image:` directly, not
# `build:`), so the executors were silently running the stock image
# with none of these dependencies — silver_transform.py's PII-masking
# UDFs failed with ModuleNotFoundError the first time they actually ran
# on an executor. No CMD override here: bitnami's own entrypoint reads
# SPARK_MODE (see docker-compose.yml) to decide master vs. worker
# startup, and silver_transform.py/pii_masking.py are bind-mounted at
# runtime (./spark:/opt/kovalyx/spark), not baked into the image.
FROM bitnamilegacy/spark:3.5.1

USER root

# hadoop-aws + the matching aws-java-sdk-bundle version it actually
# declares as a dependency, plus the Postgres JDBC driver for the
# audit-log writes in pii_masking.py/silver_transform.py. python3 (already
# present) instead of curl (not present in this image, unlike the
# apache/spark base the old version of this file assumed).
RUN python3 -c "\
import urllib.request; \
urllib.request.urlretrieve('https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar', '$SPARK_HOME/jars/hadoop-aws-3.3.4.jar'); \
urllib.request.urlretrieve('https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar', '$SPARK_HOME/jars/aws-java-sdk-bundle-1.12.262.jar'); \
urllib.request.urlretrieve('https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar', '$SPARK_HOME/jars/postgresql-42.7.3.jar')"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m spacy download en_core_web_lg

USER 1001
