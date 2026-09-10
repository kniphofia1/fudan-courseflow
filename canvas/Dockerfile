FROM rust:1-bookworm AS rust-builder

WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/data:/opt/canvas-downloader

WORKDIR /data

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m playwright install --with-deps chromium

COPY --from=rust-builder /src/target/release/canvas-downloader /usr/local/bin/canvas-downloader
COPY refresh_and_run.py /usr/local/bin/refresh_and_run.py
COPY nas /opt/canvas-downloader/nas
RUN chmod +x /usr/local/bin/canvas-downloader /usr/local/bin/refresh_and_run.py

ENTRYPOINT ["python", "/usr/local/bin/refresh_and_run.py", "--binary", "/usr/local/bin/canvas-downloader"]
CMD ["--", "-n"]
