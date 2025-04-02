FROM p09392rhel.ircqnet.com/ircqnet-rhel9-python39:latest

USER 0
RUN dnf install -y --nodocs gzip && dnf clean all

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app/app

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
