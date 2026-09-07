# BadCop: zero-dependency invoice chaser. Runs the reminder ladder once per container start;
# schedule it with cron, a systemd timer, or your platform's scheduled jobs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Mount your working directory (badcop.toml, invoices.csv, templates/, state.json) at /data.
# The container runs as root so it can write state.json and reports into the bind mount;
# pass --user "$(id -u):$(id -g)" to docker run if you want host-owned files instead.
WORKDIR /data
VOLUME ["/data"]

ENTRYPOINT ["badcop"]
CMD ["run", "--dry-run"]
