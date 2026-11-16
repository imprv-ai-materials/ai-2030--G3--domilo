# Metabase na glibc (Ubuntu jammy), bo natywna biblioteka DuckDB ze sterownika potrzebuje libstdc++, której nie ma
# w oficjalnym obrazie Metabase (Alpine, musl). Wzór: Dockerfile sterownika motherduckdb/metabase_duckdb_driver.
# metabase.jar kopiujemy z oficjalnego obrazu tej samej wersji (wspieranej przez sterownik 1.5.6.0).
FROM metabase/metabase:v0.63.17 AS metabase

FROM eclipse-temurin:21-jre-jammy
RUN groupadd -r metabase && useradd -r -g metabase -d /home/metabase -m metabase \
    && mkdir -p /app /plugins /stan /dane && chown metabase:metabase /plugins /stan
COPY --from=metabase --chown=metabase:metabase /app/metabase.jar /app/metabase.jar
USER metabase
EXPOSE 3000
CMD ["java", "-jar", "/app/metabase.jar"]
