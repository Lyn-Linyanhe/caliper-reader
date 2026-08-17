param(
    [string]$OutputDir = "E:\朱\caliper-reader-master\paper\03_排版与审校\论文图表素材\论文插图",
    [string]$BaseName = "图01_系统流程图_visio"
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

$vsdxPath = Join-Path $OutputDir "$BaseName.vsdx"
$svgPath = Join-Path $OutputDir "$BaseName.svg"
$pdfPath = Join-Path $OutputDir "$BaseName.pdf"

if (Test-Path -LiteralPath $vsdxPath) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupPath = Join-Path $OutputDir "$BaseName.backup-$stamp.vsdx"
    Copy-Item -LiteralPath $vsdxPath -Destination $backupPath
    Write-Output "Backup: $backupPath"
}

$PageW = 8.27
$PageH = 11.69
$Black = 'RGB(0,0,0)'
$White = 'RGB(255,255,255)'
$FontFormula = 'FONT("SimSun")'
$TitleFontSize = 10.5
$DetailFontSize = 8.5
$LineWeight = '0.8 pt'

function Set-Cell($shape, [string]$name, [string]$formula) {
    $shape.CellsU($name).FormulaU = $formula
}

function Set-TextStyle($shape, [double]$size, [bool]$bold = $false, [int]$align = 1) {
    Set-Cell $shape 'Char.Font' $FontFormula
    Set-Cell $shape 'Char.Size' "$size pt"
    Set-Cell $shape 'Char.Color' $Black
    Set-Cell $shape 'Char.Style' $(if ($bold) { '1' } else { '0' })
    Set-Cell $shape 'Para.HorzAlign' ([string]$align)
    Set-Cell $shape 'VerticalAlign' '1'
}

function Add-Text($page, [double]$x, [double]$y, [double]$w, [double]$h, [string]$text, [double]$size, [bool]$bold = $false) {
    $shape = $page.DrawRectangle($x, $y, ($x + $w), ($y + $h))
    Set-Cell $shape 'FillPattern' '0'
    Set-Cell $shape 'LinePattern' '0'
    $shape.Text = $text
    Set-TextStyle $shape $size $bold
    return $shape
}

function Add-Box($page, [double]$x, [double]$y, [double]$w, [double]$h, [string]$title, [string]$detail) {
    $box = $page.DrawRectangle($x, $y, ($x + $w), ($y + $h))
    Set-Cell $box 'FillPattern' '1'
    Set-Cell $box 'FillForegnd' $White
    Set-Cell $box 'LinePattern' '1'
    Set-Cell $box 'LineColor' $Black
    Set-Cell $box 'LineWeight' $LineWeight

    # Separate native text shapes keep title and detail typography independently editable.
    Add-Text $page ($x + 0.08) ($y + $h * 0.52) ($w - 0.16) ($h * 0.34) $title $TitleFontSize $true | Out-Null
    Add-Text $page ($x + 0.08) ($y + 0.10) ($w - 0.16) ($h * 0.28) $detail $DetailFontSize $false | Out-Null
    return $box
}

function Add-Arrow($page, [double]$x1, [double]$y1, [double]$x2, [double]$y2) {
    $line = $page.DrawLine($x1, $y1, $x2, $y2)
    Set-Cell $line 'LineColor' $Black
    Set-Cell $line 'LineWeight' $LineWeight
    Set-Cell $line 'BeginArrow' '0'
    Set-Cell $line 'EndArrow' '4'
    return $line
}

function Add-Line($page, [double]$x1, [double]$y1, [double]$x2, [double]$y2) {
    $line = $page.DrawLine($x1, $y1, $x2, $y2)
    Set-Cell $line 'LineColor' $Black
    Set-Cell $line 'LineWeight' $LineWeight
    return $line
}

$visio = $null
$doc = $null
try {
    $visio = New-Object -ComObject Visio.Application
    $visio.Visible = $false
    Write-Output 'Visio started.'
    $doc = $visio.Documents.Add('')
    Write-Output 'Blank document created.'
    $page = $doc.Pages.Item(1)

    Set-Cell $page.PageSheet 'PageWidth' "$PageW in"
    Set-Cell $page.PageSheet 'PageHeight' "$PageH in"
    Set-Cell $page.PageSheet 'FillPattern' '1'
    Set-Cell $page.PageSheet 'FillForegnd' $White
    Write-Output 'Page configured.'

    # Coordinates use a bottom-left origin.  The main pipeline is vertical;
    # only the two recognizers are placed side by side at the branch stage.
    $stageX = 1.65
    $stageW = 4.97
    $stageH = 0.72
    $stageRows = @(
        @(10.35, '输入图像', '固定相机采集'),
        @(8.95, 'ROI 定位', '低分辨率投影与局部精修'),
        @(7.55, '图像预处理', '灰度增强与自适应二值化'),
        @(6.15, '方向校正', '接缝 RANSAC 估计与旋转'),
        @(4.75, '区域分离', '端点接缝与谷底回退')
    )
    for ($i = 0; $i -lt $stageRows.Count; $i++) {
        $row = $stageRows[$i]
        $stageY = [double]$row[0]
        Add-Box $page $stageX $stageY $stageW $stageH $row[1] $row[2] | Out-Null
        if ($i -gt 0) {
            $previousY = [double]$stageRows[$i - 1][0]
            Add-Arrow $page ($stageX + $stageW / 2) $previousY `
                ($stageX + $stageW / 2) ($stageY + $stageH) | Out-Null
        }
    }

    # The split stage feeds two independent readers.
    $splitCenterX = $stageX + $stageW / 2
    $mainX = 0.40
    $branchY = 2.70
    $branchW = 3.25
    $branchH = 0.95
    $vernierX = 4.62
    Add-Box $page $mainX $branchY $branchW $branchH '主尺识别' '投影取峰与刻线精定位' | Out-Null
    Add-Box $page $vernierX $branchY $branchW $branchH '游标尺识别' '谷底范围、刻线检测与零线定位' | Out-Null

    $splitBottomY = 4.75
    $branchBusY = 4.05
    $mainCenterX = $mainX + $branchW / 2
    $vernierCenterX = $vernierX + $branchW / 2
    Add-Arrow $page $splitCenterX $splitBottomY $splitCenterX $branchBusY | Out-Null
    Add-Line $page $mainCenterX $branchBusY $vernierCenterX $branchBusY | Out-Null
    Add-Arrow $page $mainCenterX $branchBusY $mainCenterX ($branchY + $branchH) | Out-Null
    Add-Arrow $page $vernierCenterX $branchBusY $vernierCenterX ($branchY + $branchH) | Out-Null

    $fusionX = 1.65
    $fusionY = 1.25
    $fusionW = 4.97
    $fusionH = 0.75
    $outputX = 1.65
    $outputY = 0.22
    $outputW = 4.97
    $outputH = 0.72
    Add-Box $page $fusionX $fusionY $fusionW $fusionH '读数融合' '主尺 OCR + 游标对齐 + 读数合并' | Out-Null
    Add-Box $page $outputX $outputY $outputW $outputH '输出结果' '读数、置信度与可视化' | Out-Null

    $mainJoinX = $fusionX + 0.95
    $vernierJoinX = $fusionX + $fusionW - 0.95
    Add-Arrow $page $mainJoinX $branchY $mainJoinX ($fusionY + $fusionH) | Out-Null
    Add-Arrow $page $vernierJoinX $branchY $vernierJoinX ($fusionY + $fusionH) | Out-Null
    Add-Arrow $page ($fusionX + $fusionW / 2) $fusionY `
        ($outputX + $outputW / 2) ($outputY + $outputH) | Out-Null
    Write-Output 'Native shapes drawn.'

    $doc.SaveAs($vsdxPath) | Out-Null
    Write-Output 'VSDX saved.'
    $page.Export($svgPath)
    Write-Output 'SVG exported.'
    # 1 = PDF, 1 = print quality, 0 = all pages.
    $doc.ExportAsFixedFormat(1, $pdfPath, 1, 0)
    Write-Output "VSDX: $vsdxPath"
    Write-Output "SVG:  $svgPath"
    Write-Output "PDF:  $pdfPath"
}
finally {
    if ($doc -ne $null) {
        try { $doc.Close() } catch {}
    }
    if ($visio -ne $null) {
        try { $visio.Quit() } catch {}
    }
}
