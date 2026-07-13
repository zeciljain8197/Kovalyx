FROM apache/spark:3.5.0-python3

USER root

# hadoop-aws + the matching aws-java-sdk-bundle version it actually
# declares as a dependency, plus the Postgres JDBC driver for the
# audit-log writes in pii_masking.py/silver_transform.py.
RUN curl -fsSL -o "$SPARK_HOME/jars/hadoop-aws-3.3.4.jar" \
        https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -fsSL -o "$SPARK_HOME/jars/aws-java-sdk-bundle-1.12.262.jar" \
        https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && curl -fsSL -o "$SPARK_HOME/jars/postgresql-42.7.3.jar" \
        https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_lg

COPY silver_transform.py pii_masking.py ./

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["spark-submit", "/app/silver_transform.py"]
