FROM python:3.11-slim

WORKDIR /app

# Install dependencies directly
RUN pip install --no-cache-dir fastapi uvicorn chromadb python-dotenv pydantic-settings langchain langchain-community langchain-chroma langchain-google-genai

# Copy application files (app directory and main.py entrypoint)
COPY main.py ./
COPY app/ ./app/

# Default environment configuration
ENV CHROMA_MODE=docker
ENV CHROMA_HOST=chromadb
ENV CHROMA_PORT=8000
ENV PORT=8000

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
