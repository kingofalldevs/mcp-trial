FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY server.py .
COPY public/ public/

# Expose port (default 8000, dynamically overridden by PORT env var)
EXPOSE 8000

ENV PORT=8000

CMD ["python", "server.py"]
