import os
from pathlib import Path

url = (
    os.environ.get("FF_SUPABASE_URL")
    or os.environ.get("PALACIO_SUPABASE_URL")
    or ""
).strip()

key = (
    os.environ.get("FF_SUPABASE_ANON_KEY")
    or os.environ.get("PALACIO_SUPABASE_ANON_KEY")
    or ""
).strip()

if not url:
    raise SystemExit(
        "ERROR: falta PALACIO_SUPABASE_URL/FF_SUPABASE_URL."
    )

if not key:
    raise SystemExit(
        "ERROR: falta PALACIO_SUPABASE_ANON_KEY/FF_SUPABASE_ANON_KEY."
    )

if not url.startswith("https://"):
    raise SystemExit(
        "ERROR: la URL de Supabase no es válida."
    )

target = Path.cwd() / "build_config.py"

target.write_text(
    "SUPABASE_URL = " + repr(url) + "\n"
    + "SUPABASE_ANON_KEY = " + repr(key) + "\n",
    encoding="utf-8",
)

print("Backend configuration generated.")
print("Supabase URL:", url)
print("Anon key: present")
print("Target:", target)
