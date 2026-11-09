param(
    [Parameter(Position = 0)]
    [ValidateSet('Prepare', 'Start', 'Stop', 'Check', 'Test', 'Seed', 'Backup', 'Restore')]
    [string]$Action = 'Start',
    [string[]]$TestLabels = @(),
    [string]$BackupFile,
    [string]$DatabaseName,
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')]
    [string]$ProjectName,
    [ValidateRange(0, 65535)]
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
if ($Port) { $env:DJANGO_PORT = [string]$Port }

function Invoke-Compose {
    if ($ProjectName) { & docker compose --project-name $ProjectName @args }
    else { & docker compose @args }
    if ($LASTEXITCODE -ne 0) { throw "docker compose fallo (codigo $LASTEXITCODE)." }
}

try {
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
        Write-Host 'Se creo .env para desarrollo. Revisa sus valores antes de compartir el equipo.'
    }
    switch ($Action) {
        Prepare { Invoke-Compose build web; Invoke-Compose pull db }
        Start {
            Invoke-Compose up -d --wait --pull never --no-build
            $binding = Invoke-Compose port web 8000
            $publishedPort = ($binding | Select-Object -First 1) -replace '^.*:', ''
            Write-Host "http://localhost:$publishedPort"
        }
        Stop { Invoke-Compose down }
        Check {
            Invoke-Compose run --rm --no-deps --entrypoint python web manage.py check
            Invoke-Compose run --rm --no-deps --entrypoint python web manage.py makemigrations --check --dry-run
        }
        Test {
            Invoke-Compose up -d --wait --pull never db
            Invoke-Compose run --rm --no-deps --entrypoint python web manage.py test --settings=butacaCero.test_settings @TestLabels
        }
        Seed { Invoke-Compose exec web python manage.py seed_practice }
        Backup {
            if (-not $BackupFile) { $BackupFile = Join-Path $repoRoot ('backups/local-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dump') }
            $backupPath = [IO.Path]::GetFullPath($BackupFile)
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupPath) | Out-Null
            # Copy the binary dump directly; PowerShell 5 redirection corrupts binary streams.
            Invoke-Compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/butaca-local.dump'
            Invoke-Compose cp db:/tmp/butaca-local.dump $backupPath
            Write-Host "Backup: $backupPath. Copia tambien django/media para conservar imagenes."
        }
        Restore {
            if (-not $BackupFile -or -not (Test-Path -LiteralPath $BackupFile)) { throw 'Indica -BackupFile con un backup existente.' }
            if ($DatabaseName -notmatch '^[a-zA-Z][a-zA-Z0-9_]{0,62}$') { throw 'Indica -DatabaseName para una base NUEVA (letras, numeros y _).' }
            $backupPath = (Resolve-Path -LiteralPath $BackupFile).Path
            Invoke-Compose cp $backupPath db:/tmp/butaca-restore.dump
            # createdb fails if the database exists. Never overwrite the usual database.
            Invoke-Compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh $DatabaseName
            Invoke-Compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error /tmp/butaca-restore.dump' sh $DatabaseName
            Write-Host "Restaurado en la base nueva $DatabaseName. La base habitual no fue reemplazada."
        }
    }
} finally {
    Pop-Location
}
