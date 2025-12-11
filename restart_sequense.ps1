param (
    [Parameter(Mandatory = $true)]
    [string]$FolderPath
)

# Check if folder exists
if (-not (Test-Path $FolderPath)) {
    Write-Error "Folder not found: $FolderPath"
    exit
}

# Ask if user wants to rename in a new temp folder
$UseTempFolder = Read-Host "Do you want to rename files in a new temp folder? (Y/N)"
$TempFolder = $FolderPath

if ($UseTempFolder -match '^[Yy]$') {
    $ParentDir = Split-Path $FolderPath -Parent
    $TempFolder = Join-Path $ParentDir "temp"
    if (-not (Test-Path $TempFolder)) { New-Item -ItemType Directory -Path $TempFolder | Out-Null }
    Write-Host "Files will be renamed in temp folder: $TempFolder"
}

# Ask if user wants to restore original names instead
$Restore = Read-Host "Do you want to restore original names from mapping? (Y/N)"

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$MappingFile = Join-Path $DesktopPath "rename_mapping.csv"

if ($Restore -match '^[Yy]$') {
    if (-not (Test-Path $MappingFile)) {
        Write-Error "Mapping file not found: $MappingFile"
        exit
    }

    $Mappings = Import-Csv -Path $MappingFile
    foreach ($map in $Mappings) {
        $NewPath = Join-Path $FolderPath $map.NewName
        $OldPath = Join-Path $FolderPath $map.OldName
        if (Test-Path $NewPath) {
            Rename-Item -Path $NewPath -NewName $map.OldName
            Write-Host "Restored: $($map.NewName) -> $($map.OldName)"
        } else {
            Write-Warning "File not found: $($map.NewName)"
        }
    }
    Write-Host "`nRestore completed."
    exit
}

# Get all .jp2 files in folder
$Files = Get-ChildItem -Path $FolderPath -Filter "*.jp2" | Sort-Object Name

$Counter = 0
$RenameList = @()
$SkippedFiles = @()

foreach ($File in $Files) {
    if ($File.BaseName -match "^(.*?)(\d{4,5})(_[a-zA-Z])$") {
        $BaseName = $matches[1]
        $NumberLength = $matches[2].Length
        $Suffix = $matches[3]
        $NewNumber = "{0:D$NumberLength}" -f $Counter
        $NewName = "${BaseName}${NewNumber}${Suffix}.jp2"

        $RenameList += [PSCustomObject]@{
            OldName = $File.Name
            NewName = $NewName
            FullPath = $File.FullName
        }

        $Counter++
    } else {
        $SkippedFiles += $File.Name
    }
}

# Display skipped files
if ($SkippedFiles.Count -gt 0) {
    Write-Host "`nWarning: The following files were skipped (pattern not matched):"
    $SkippedFiles | ForEach-Object { Write-Host $_ }
}

# Display proposed renames
Write-Host "`nThe following files will be renamed:`n"
$RenameList | ForEach-Object { Write-Host "$($_.OldName)  -->  $($_.NewName)" }

# Ask for confirmation
$Confirmation = Read-Host "`nDo you want to proceed with renaming? (Y/N)"
if ($Confirmation -match '^[Yy]$') {

    foreach ($Item in $RenameList) {
        $NewFullPath = Join-Path -Path $TempFolder -ChildPath $Item.NewName


        if ($UseTempFolder -match '^[Yy]$') {
            Copy-Item -Path $Item.FullPath -Destination $NewFullPath
        } else {
            Rename-Item -Path $Item.FullPath -NewName $NewFullPath
        }
    }

    # Save mapping for reversibility
    $RenameList | Select-Object OldName, NewName | Export-Csv -Path $MappingFile -NoTypeInformation
    Write-Host "`nOperation completed successfully."
    Write-Host "Mapping file saved at: $MappingFile"
} else {
    Write-Host "`nOperation cancelled. No files were renamed."
}
