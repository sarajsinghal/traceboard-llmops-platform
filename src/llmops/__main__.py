import argparse
import uvicorn

parser = argparse.ArgumentParser(description="Project 17 local LLMOps API")
parser.add_argument("command", choices=["api"])
args = parser.parse_args()
uvicorn.run("llmops.api:app", host="127.0.0.1", port=8000, reload=False)
