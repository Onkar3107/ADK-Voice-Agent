# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (needed for audio libraries)
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Google ADK / GenAI libs might not be in pypi yet or require specific handling
# Assuming they are handled via requirements or local files
# If 'google-adk' is a local package, we would need to copy it.
# For now, we assume requirements.txt is sufficient.

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
# We use shell form to allow variable expansion if needed, but array form is safer.
# Using python directly as entrypoint.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
