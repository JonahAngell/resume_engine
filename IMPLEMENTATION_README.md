# Application version implementation

Apply these replacement files at the repository root. Then run `npm install` to refresh the root lockfile, because the supplied patch intentionally does not replace the current lockfile when no dependency changed.

For a local build with the current Git SHA:

```powershell
$sha = git rev-parse --short=7 HEAD
docker compose build --build-arg VITE_BUILD_SHA=$sha app
docker compose up
```

A normal `docker compose up --build` displays `Build local`.
