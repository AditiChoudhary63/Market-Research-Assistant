"""
Application entry point.
Run with:  python main.py
Or:        uvicorn api:app --reload
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
