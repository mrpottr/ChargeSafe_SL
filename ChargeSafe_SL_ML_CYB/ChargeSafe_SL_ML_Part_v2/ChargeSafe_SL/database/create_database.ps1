$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

if (-not (Test-Path $envFile)) {
    Write-Error ".env file not found. Copy .env.example to .env and set your PostgreSQL credentials first."
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
        return
    }

    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1])
        Set-Item -Path "Env:$($parts[0])" -Value $parts[1]
    }
}

$schemaPath = Join-Path $PSScriptRoot "init\\001_schema.sql"
$dbName = $env:POSTGRES_DB

if (-not $dbName) {
    Write-Error "POSTGRES_DB is not set in .env."
    exit 1
}

Write-Host "Creating database '$dbName' if it does not already exist..."
$dbExists = psql -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d postgres `
    -tAc "SELECT 1 FROM pg_database WHERE datname = '$dbName';"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Database existence check failed."
    exit $LASTEXITCODE
}

if (-not ($dbExists | Select-String -Pattern "1")) {
    psql -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d postgres `
        -c "CREATE DATABASE ""$dbName"";"

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Database creation step failed."
        exit $LASTEXITCODE
    }
}

Write-Host "Applying schema from $schemaPath ..."
psql -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d $dbName -f $schemaPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "Schema import failed."
    exit $LASTEXITCODE
}

Write-Host "Database setup completed successfully."
