FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY elevator_sim/ ./elevator_sim/
COPY scripts/ ./scripts/
COPY example_files/ ./example_files/

RUN python -m pip install --upgrade pip \
    && python -m pip install .


FROM base AS test

COPY unit_tests/ ./unit_tests/

RUN python -m unittest discover -s unit_tests -v \
    && touch /tmp/tests-passed


FROM base AS runtime

# This creates a dependency on the test stage, ensuring tests run, without
# copying the test suite into the final image.
COPY --from=test /tmp/tests-passed /tmp/tests-passed

RUN mkdir -p /data /results

ENTRYPOINT ["elevator-sim"]
CMD ["--help"]