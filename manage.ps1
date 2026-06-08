param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "restart", "logs", "ps", "build", "migrate", "seed", "backup")]
    [string]$Action = "up"
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

switch ($Action) {
    "up" { docker compose up -d --build }
    "down" { docker compose down }
    "restart" { docker compose restart }
    "logs" { docker compose logs -f }
    "ps" { docker compose ps }
    "build" { docker compose build }
    "migrate" { docker compose exec backend alembic upgrade head }
    "seed" { docker compose exec backend python -m app.scripts.seed }
    "backup" { bash ./scripts/backup.sh }
    default { docker compose up -d --build }
}

Write-Host "Done: $Action"
