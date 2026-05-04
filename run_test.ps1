$ProjectRoot = "C:\Program Files(1)(x86)\Sutra.AI\Sutra.AI"
$SubmissionId = "sutra-ai-assessment"
$RepoUrl = "https://github.com/Konika-Thakur/Sutra.AI.git"
$TempRoot = Join-Path $env:TEMP "sutra-ai-assessment"
$CodePath = Join-Path $TempRoot "submission_repo"
$DocxPath = "$ProjectRoot\Sutra_AI_Overview.docx"
$PdfPath = "$ProjectRoot\Sutra_AI_Overview.pdf"
$PptxPath = "$ProjectRoot\Sutra_AI_Overview.pptx"
$VideoPath = "$ProjectRoot\audio_for_test 1.mp4"
$OutputPath = "$ProjectRoot\test_outputs\$SubmissionId.json"

New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath) | Out-Null
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

if (-not (Test-Path "$CodePath\.git")) {
  if (Test-Path $CodePath) {
    Remove-Item -Recurse -Force $CodePath
  }
  git clone --depth 1 $RepoUrl $CodePath
}

if (-not (Test-Path $DocxPath)) {
  Write-Host "Warning: DOCX not found: $DocxPath"
}

if (-not (Test-Path $PdfPath)) {
  Write-Error "PDF deck not found: $PdfPath"
  exit 1
}

if (-not (Test-Path $PptxPath)) {
  Write-Error "PPTX deck not found: $PptxPath"
  exit 1
}

if (-not (Test-Path $VideoPath)) {
  Write-Error "Video file not found: $VideoPath"
  exit 1
}

$Command = @(
  "$ProjectRoot\main.py",
  "--submission-id", $SubmissionId,
  "--deck", $PdfPath, $PptxPath,
  "--video", $VideoPath,
  "--code", $CodePath,
  "--output", $OutputPath
)

py @Command

if ($LASTEXITCODE -eq 0) {
  Write-Host "Assessment output written to: $OutputPath"
}

exit $LASTEXITCODE
