<#
.SYNOPSIS
    Code signing helper for Trackora.
.DESCRIPTION
    Creates a self-signed certificate for development/testing and
    signs the Trackora executable. For production, replace the
    self-signed cert with a trusted certificate from a CA.
.PARAMETER ExecutablePath
    Path to the executable to sign. Default: dist/Trackora.exe
.PARAMETER CertSubject
    Subject name for the self-signed certificate.
    Default: "CN=Trackora, O=Trackora, C=US"
.PARAMETER OutputDir
    Where to store the generated certificate files.
    Default: certs/
.EXAMPLE
    # Create a self-signed cert and sign the executable:
    .\scripts\sign-code.ps1

    # Sign with an existing certificate:
    .\scripts\sign-code.ps1 -CertPath "C:\path\to\certificate.pfx"
#>

param(
    [string]$ExecutablePath = "dist\Trackora.exe",
    [string]$CertSubject = "CN=Trackora, O=Trackora, C=US",
    [string]$OutputDir = "certs"
)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------ #
# Helper: check if a command exists
# ------------------------------------------------------------------ #
function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

# ------------------------------------------------------------------ #
# Step 1: Install prerequisites
# ------------------------------------------------------------------ #
Write-Host "=== Trackora Code Signing ===" -ForegroundColor Cyan

# Check for signtool (comes with Windows SDK)
if (-not (Test-Command "signtool")) {
    Write-Host "WARNING: signtool not found. Install Windows SDK:" -ForegroundColor Yellow
    Write-Host "  https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/"
    Write-Host "Or install Visual Studio with the 'Desktop development with C++' workload."
    exit 1
}

# ------------------------------------------------------------------ #
# Step 2: Create output directory
# ------------------------------------------------------------------ #
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    Write-Host "Created directory: $OutputDir" -ForegroundColor Green
}

# ------------------------------------------------------------------ #
# Step 3: Generate or locate the certificate
# ------------------------------------------------------------------ #
$pfxPath = Join-Path $OutputDir "Trackora-dev.pfx"
$cerPath = Join-Path $OutputDir "Trackora-dev.cer"

if (-not (Test-Path $pfxPath)) {
    Write-Host "Generating self-signed certificate..." -ForegroundColor Yellow
    Write-Host "  Subject: $CertSubject"
    Write-Host "  PFX:     $pfxPath"
    Write-Host "  CER:     $cerPath"

    # Create a self-signed certificate
    $cert = New-SelfSignedCertificate `
        -Subject $CertSubject `
        -FriendlyName "Trackora Development" `
        -Type CodeSigning `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(3)

    # Export to PFX (with private key) and CER (public key only)
    $password = ConvertTo-SecureString -String "TrackoraDev" -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null
    Export-Certificate -Cert $cert -FilePath $cerPath -Type CERT | Out-Null

    Write-Host "Certificate generated." -ForegroundColor Green
} else {
    Write-Host "Using existing certificate: $pfxPath" -ForegroundColor Green
}

# ------------------------------------------------------------------ #
# Step 4: Sign the executable
# ------------------------------------------------------------------ #
if (-not (Test-Path $ExecutablePath)) {
    Write-Host "ERROR: Executable not found: $ExecutablePath" -ForegroundColor Red
    Write-Host "Build the executable first with: pyinstaller Trackora.spec"
    exit 1
}

Write-Host "`nSigning executable: $ExecutablePath" -ForegroundColor Yellow

$timestampServer = "http://timestamp.digicert.com"

if (Test-Path $pfxPath) {
    & signtool sign `
        /fd SHA256 `
        /a `
        /f $pfxPath `
        /p "TrackoraDev" `
        /tr $timestampServer `
        /td SHA256 `
        $ExecutablePath
} else {
    # Try signing with a certificate from the store
    & signtool sign `
        /fd SHA256 `
        /a `
        /tr $timestampServer `
        /td SHA256 `
        $ExecutablePath
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Successfully signed!" -ForegroundColor Green

    # Verify the signature
    Write-Host "`nVerifying signature..." -ForegroundColor Cyan
    & signtool verify /pa $ExecutablePath
} else {
    Write-Host "`n✗ Signing failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------ #
# Step 5: Summary
# ------------------------------------------------------------------ #
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
Write-Host "  Certificate (PFX): $pfxPath"
Write-Host "  Certificate (CER): $cerPath"
Write-Host "  Signed executable: $ExecutablePath"
Write-Host ""
Write-Host "NOTE: This is a SELF-SIGNED certificate." -ForegroundColor Yellow
Write-Host "For production, replace it with a certificate from a trusted CA:" -ForegroundColor Yellow
Write-Host "  - DigiCert:  https://www.digicert.com/"
Write-Host "  - Sectigo:   https://sectigo.com/"
Write-Host "  - GlobalSign: https://www.globalsign.com/"
Write-Host ""
Write-Host "After obtaining a real certificate, run this script again" -ForegroundColor Yellow
Write-Host "  or sign manually with:" -ForegroundColor Yellow
Write-Host "  signtool sign /fd SHA256 /a /f your-cert.pfx /p your-password /tr http://timestamp.digicert.com /td SHA256 dist\Trackora.exe"
