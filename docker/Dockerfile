# One image for every Spark container (masters, workers) and for the controller.
# Spark 3.5.3 ships with Hadoop 3.3.4, so the S3A connector versions below must match it.
FROM apache/spark:3.5.3

USER root

# iproute2 -> `tc netem` for network-delay faults; procps -> `pkill` for executor-kill faults.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 procps curl util-linux \
 && rm -rf /var/lib/apt/lists/*

# S3A connector so Spark can read/write MinIO (shared checkpoint + data store).
RUN curl -fsSL -o /opt/spark/jars/hadoop-aws-3.3.4.jar \
      https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
 && curl -fsSL -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar \
      https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar

COPY docker/requirements-container.txt /tmp/requirements-container.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements-container.txt \
 && ln -sf /usr/bin/python3 /usr/local/bin/python   # README commands call `python`

COPY docker/spark-defaults.conf /opt/spark/conf/spark-defaults.conf
COPY docker/metrics.properties  /opt/spark/conf/metrics.properties

ENV PYTHONPATH=/workspace \
    PATH=$PATH:/opt/spark/bin \
    PYSPARK_PYTHON=python3

WORKDIR /workspace
