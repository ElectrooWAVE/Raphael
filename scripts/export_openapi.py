"""Export OpenAPI schema from FastAPI backend to frontend/openapi.json."""
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app

def main():
    out_dir = PROJECT_ROOT / "frontend"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "openapi.json"
    
    schema = app.openapi()
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        
    print(f"OpenAPI schema successfully exported to: {out_file} ({out_file.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
