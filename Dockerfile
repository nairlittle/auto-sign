FROM python:3.10-slim

# Install runtime libs required by ddddocr/onnxruntime and timezone data.
RUN apt-get update && apt-get install -y \
    libgomp1 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
