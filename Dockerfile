FROM python:3.13-slim

# ffmpeg is used to generate synthetic test content and for future transcode;
# it is not needed on the hub's relay hot path.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY hub/requirements.txt ./hub/requirements.txt
RUN pip install --no-cache-dir -r hub/requirements.txt

COPY hub/ ./hub/
COPY testkit/ ./testkit/
COPY portal_sim/ ./portal_sim/

ENV STREAMOS_DATA=/data
VOLUME /data
EXPOSE 8099
CMD ["python", "-m", "uvicorn", "streamos.main:app", \
     "--app-dir", "hub", "--host", "0.0.0.0", "--port", "8099"]
