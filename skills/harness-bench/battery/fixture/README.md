# flowkit

A small codebase that summarizes zone flow readings.

The entry point is [app/main.py](app/main.py); zones are summarized by [the util module](app/util.py) and every reading is clamped by [the helpers](app/helpers.py).

Run the tests with:

```bash
python3 -m unittest discover -s tests -t .
```
