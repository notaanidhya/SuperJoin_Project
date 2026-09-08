import os
import sys
import uvicorn
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    print("=" * 80)
    print("SUPERJOIN FACT KNOWLEDGE LAYER - STARTING SERVER")
    print("=" * 80)
    print("Serving on http://localhost:8000")
    print("  - Inspection Dashboard UI: http://localhost:8000/")
    print("  - Interactive OpenAPI Docs: http://localhost:8000/docs")
    print("  - Knowledge Layer Stats:   http://localhost:8000/api/stats")
    print("  - The 4 Showcase Cases:    http://localhost:8000/api/showcase")
    print("=" * 80)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        app_dir=str(backend_dir)
    )
