param(
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

$targetNames = @(
    '.pytest_cache',
    '.pytest_tmp_table2',
    '.docx_render_table2',
    '__pycache__',
    '.pytest_tmp_reference_audit',
    'tmp_pytest_paper_audit',
    '.tmp_edge_profile_audit',
    '.tmp_edge_profile_audit_2',
    '.tmp_lo_profile_audit',
    '.tmp_lo_profile_audit_v2',
    '.tmp_lo_profile_png',
    'tmp_std_check',
    'paper_render_audit'
)

$targets = @($targetNames | ForEach-Object { Join-Path $root $_ })
$targets += @(
    (Join-Path $root '.tmp_batch_audit_output.jsonl'),
    (Join-Path $root '.tmp_config_audit_report.md'),
    (Join-Path $root '.tmp_config_reads_current.txt'),
    (Join-Path $root '.tmp_defs.txt'),
    (Join-Path $root '.tmp_defs_current.txt')
)
$targets += @(Get-ChildItem -LiteralPath $root -File | Where-Object {
    $_.Name -like 'debug_*.png' -or $_.Name -like 'tmp_*.png'
} | Select-Object -ExpandProperty FullName)

function Get-Bytes($path) {
    if ([IO.File]::Exists($path)) {
        return ([IO.FileInfo]$path).Length
    }
    if ([IO.Directory]::Exists($path)) {
        $sum = (Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) { return [int64]0 }
        return [int64]$sum
    }
    return [int64]0
}

$items = @()
foreach ($candidate in $targets) {
    $full = [IO.Path]::GetFullPath($candidate)
    if (-not ([IO.File]::Exists($full) -or [IO.Directory]::Exists($full))) { continue }
    $inside = $full.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or
        $full.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
    if (-not $inside) { throw "Refusing path outside workspace: $full" }

    $relative = $full.Substring($root.Length).TrimStart('\', '/')
    $tracked = @(git -C $root ls-files -- $relative)
    if ($tracked.Count -gt 0) { throw "Refusing tracked path: $relative" }
    $items += [PSCustomObject]@{ Path = $full; Relative = $relative; Bytes = (Get-Bytes $full) }
}

$total = ($items | Measure-Object -Property Bytes -Sum).Sum
Write-Output ("Verified {0} untracked scratch targets; {1:N0} bytes." -f $items.Count, $total)
foreach ($item in $items) {
    Write-Output ("{0} ({1:N0} bytes)" -f $item.Relative, $item.Bytes)
    if ($WhatIf) { continue }
    try {
        if ([IO.File]::Exists($item.Path)) {
            [IO.File]::Delete($item.Path)
        } elseif ([IO.Directory]::Exists($item.Path)) {
            [IO.Directory]::Delete($item.Path, $true)
        }
    } catch {
        Write-Warning ("Skipped {0}: {1}" -f $item.Relative, $_.Exception.Message)
    }
}

if ($WhatIf) {
    Write-Output 'WhatIf: no files were removed.'
} else {
    Write-Output 'Cleanup completed.'
}
