
from fastapi import FastAPI

app = FastAPI(
    title="HR Copilot API",
    description="AI-powered Human Resource Management System",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "Welcome to HR Copilot API",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }
