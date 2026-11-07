# The windows-2025 runner uses Server build 26100. Fetch just the signed CABs
# from Microsoft's matching Languages and Optional Features ISO. Windows Update
# feature discovery can hang on hosted runners. Byte ranges identify whole
# files in this pinned image; validate each file before passing it to DISM.
$ErrorActionPreference = 'Stop'
$iso = 'https://software-static.download.prss.microsoft.com/dbazure/888969d5-f34g-4e03-ac9d-1f9786c66749/26100.1.240331-1435.ge_release_amd64fre_SERVER_LOF_PACKAGES_OEM.iso'
$packages = @(
    @('Basic-ja-jp', '726542336-787132801')
    @('OCR-ja-jp', '2045255680-2046782463')
    @('Basic-ko-kr', '805877760-815622131')
    @('OCR-ko-kr', '2046783488-2050191283')
    @('Basic-ru-ru', '973547520-986008516')
    @('OCR-ru-ru', '2051182592-2051344053')
)
foreach ($package in $packages) {
    $feature, $range = $package
    [long]$first, [long]$last = $range.Split('-')
    $length = $last - $first + 1
    $cab = Join-Path $env:RUNNER_TEMP "Microsoft-Windows-LanguageFeatures-$feature-Package~31bf3856ad364e35~amd64~~.cab"
    curl.exe --fail --silent --show-error --location --retry 2 --max-time 180 --max-filesize $length --range $range --output $cab "${iso}?feature=$feature"
    if ($LASTEXITCODE -ne 0 -or (Get-Item -LiteralPath $cab).Length -ne $length) {
        throw "Failed to retrieve the pinned $feature package."
    }
    $catalogDir = New-Item -ItemType Directory -Path (Join-Path $env:RUNNER_TEMP $feature) -Force
    expand.exe -F:update.cat $cab $catalogDir.FullName | Out-Null
    $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $catalogDir 'update.cat')
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "Invalid Microsoft package catalog for $feature."
    }
    Add-WindowsPackage -Online -PackagePath $cab -NoRestart -ErrorAction Stop | Out-Host
}
& ./.venv/Scripts/python.exe -c "from winrt.windows.media.ocr import OcrEngine; tags = {l.language_tag.split('-')[0] for l in OcrEngine.available_recognizer_languages}; print('Installed OCR:', sorted(tags)); assert {'ja', 'ko', 'ru'} <= tags"
exit $LASTEXITCODE
