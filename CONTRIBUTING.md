# Contributing

Issues and pull requests are welcome. Each bot lives in `bots/<name>/` and should stay runnable on its own
(`.env.example`, `Dockerfile`, short README). Never commit tokens or `.env` files.

Before opening a PR, make sure the CI checks pass locally:

```bash
python3 -m compileall -q bots        # Python bots
for f in bots/chef-roast/src/*.js bots/chef-roast/src/*/*.js; do node --check "$f"; done
```
