# OpenRouter key test

No installs needed (Python 3.8+, standard library only).

1. Put `test_openrouter_key.py` in the folder that contains your `.env`
   (or pass `--env path/to/.env`).
2. `.env` must contain: `OPENROUTER_API_KEY=sk-or-...`
   Optional: `OPENROUTER_MODEL=<some-model>:free`
3. Run:
       python test_openrouter_key.py
       python test_openrouter_key.py --model openrouter/free
