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
    port = int(os.environ.get("PORT", 8000))
    print(f"Serving on http://0.0.0.0:{port}")
    print(f"  - Inspection Dashboard UI: http://localhost:{port}/")
    print(f"  - Interactive OpenAPI Docs: http://localhost:{port}/docs")
    print(f"  - Knowledge Layer Stats:   http://localhost:{port}/api/stats")
    print(f"  - The 4 Showcase Cases:    http://localhost:{port}/api/showcase")
    print("=" * 80)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        app_dir=str(backend_dir)
    )
