"""Agent OS brain package. Loads .env (if present) so integration tokens reach the whole brain."""

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional — the brain runs fine without it (just no .env autoload)
    pass
