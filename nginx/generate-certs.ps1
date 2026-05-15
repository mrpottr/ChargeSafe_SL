# generate-certs.ps1
# Generates a self-signed SSL certificate for local HTTPS development.
# Uses Docker (no OpenSSL installation required on Windows).
# Run this once from the project root: .\nginx\generate-certs.ps1

$certsDir = Join-Path $PSScriptRoot "certs"

if (-not (Test-Path $certsDir)) {
    New-Item -ItemType Directory -Path $certsDir | Out-Null
    Write-Host "Created directory: $certsDir"
}

Write-Host "Generating self-signed SSL certificate via Docker..."

docker run --rm `
    -v "${certsDir}:/certs" `
    alpine/openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
    -keyout /certs/server.key `
    -out /certs/server.crt `
    -subj "/C=LK/ST=Western/L=Colombo/O=ChargeSafe/OU=Security/CN=localhost"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS: Certificates generated in $certsDir" -ForegroundColor Green
    Write-Host "  - server.crt (public certificate)"
    Write-Host "  - server.key (private key)"
    Write-Host ""
    Write-Host "Now run: docker-compose up -d nginx" -ForegroundColor Cyan
    Write-Host "Then access: https://localhost:8443/api/stations"
} else {
    Write-Host "FAILED: Could not generate certificates." -ForegroundColor Red
    Write-Host "Make sure Docker is running and try again."
}
