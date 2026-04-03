$parentDir = "C:\Your\Parent\Folder"

Import-Csv "your_data.csv" | ForEach-Object {
    $currentLookup = $_.lookup
    $currentReplace = $_.replacewith

    # Search for any subfolder containing the lookup string
    $targetFolder = Get-ChildItem -Path $parentDir -Directory -Filter "*$currentLookup*" | Select-Object -First 1

    if ($targetFolder) {
        Write-Host "Found matching folder: $($targetFolder.FullName)" -ForegroundColor Cyan
        
        # Run your script using the found folder's full path
        .\rename.ps1 -folder "$($targetFolder.FullName)" -lookup $currentLookup -replacewith $currentReplace
    } else {
        Write-Warning "No folder found containing: $currentLookup"
    }
}
