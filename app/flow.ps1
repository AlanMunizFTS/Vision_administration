param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "machines.json")
)

# ============================================================
# FTS DWH Sync desde JSON - solo sync.log
# ------------------------------------------------------------
# Este script:
#   1. Lee estaciones desde JSON.
#   2. Exporta cada DB remota por SSH.
#   3. Guarda .sql en carpeta diaria Database_ddMMyy.
#   4. Transforma el SQL con add_to_database_central.py.
#   5. Importa a PostgreSQL central.
#   6. Guarda TODO el log en un unico archivo:
#        C:\FTS_SYNC\Database_ddMMyy\logs\sync.log
#   7. Elimina SQL temporal centralizado despues de importar.
#
# IMPORTANTE:
#   La retencion solo elimina carpetas Database_* antiguas.
#   No elimina datos dentro de PostgreSQL.
# ============================================================

$ErrorActionPreference = "Stop"

# ---------------- FUNCIONES BASE ----------------

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp][$Level] $Message"

    Write-Host $line

    if ($script:MainLog) {
        Add-Content -Path $script:MainLog -Value $line
    }
}

function Quote-CmdArg {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    return '"' + ($Value -replace '"', '\"') + '"'
}

function Invoke-CmdLine {
    param(
        [Parameter(Mandatory = $true)][string]$CommandLine,
        [Parameter(Mandatory = $true)][string]$StepName
    )

    & cmd.exe /d /s /c $CommandLine
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        throw "$StepName fallo con ExitCode=$exitCode"
    }

    return $exitCode
}

function Resolve-PathFromScriptRoot {
    param(
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return (Join-Path $PSScriptRoot $PathValue)
}

function Assert-CommandExists {
    param(
        [Parameter(Mandatory = $true)][string]$CommandName
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "No se encontro '$CommandName' en PATH."
    }
}

function Load-Config {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "No se encontro el archivo de configuracion: $Path"
    }

    try {
        return Get-Content -Path $Path -Raw | ConvertFrom-Json
    }
    catch {
        throw "No se pudo leer/parsear el JSON '$Path'. Error: $($_.Exception.Message)"
    }
}

function Test-Config {
    param(
        [Parameter(Mandatory = $true)]$Config
    )

    if (-not $Config.paths.base_sync_dir) {
        throw "Falta paths.base_sync_dir en el JSON."
    }

    if (-not $Config.paths.add_to_central_script) {
        throw "Falta paths.add_to_central_script en el JSON."
    }

    if (-not $Config.paths.logs_folder_name) {
        throw "Falta paths.logs_folder_name en el JSON."
    }

    if (-not $Config.retention.folder_prefix) {
        throw "Falta retention.folder_prefix en el JSON."
    }

    if (-not $Config.retention.date_format) {
        throw "Falta retention.date_format en el JSON."
    }

    if (-not $Config.ssh.user) {
        throw "Falta ssh.user en el JSON."
    }

    if (-not $Config.ssh.remote_command) {
        throw "Falta ssh.remote_command en el JSON."
    }

    if (-not $Config.postgres.docker_container) {
        throw "Falta postgres.docker_container en el JSON."
    }

    if (-not $Config.postgres.database) {
        throw "Falta postgres.database en el JSON."
    }

    if (-not $Config.postgres.user) {
        throw "Falta postgres.user en el JSON."
    }

    if (-not $Config.stations -or $Config.stations.Count -eq 0) {
        throw "No hay estaciones definidas en stations."
    }

    foreach ($station in $Config.stations) {
        if (-not $station.name) {
            throw "Hay una estacion sin name."
        }

        if (-not $station.ip) {
            throw "La estacion '$($station.name)' no tiene ip."
        }

        if (-not $station.output_file) {
            throw "La estacion '$($station.name)' no tiene output_file."
        }
    }
}

function Remove-OldDatabaseFolders {
    param(
        [Parameter(Mandatory = $true)][string]$BaseSyncDir,
        [Parameter(Mandatory = $true)][string]$FolderPrefix,
        [Parameter(Mandatory = $true)][string]$DateFormat,
        [Parameter(Mandatory = $true)][int]$RetentionDays
    )

    Write-Log "Revisando retencion. Se conservaran carpetas de los ultimos $RetentionDays dias."

    $limitDate = (Get-Date).Date.AddDays(-$RetentionDays)
    $folders = Get-ChildItem -Path $BaseSyncDir -Directory -Filter "$FolderPrefix*" -ErrorAction SilentlyContinue

    foreach ($folder in $folders) {
        $dateText = $folder.Name.Substring($FolderPrefix.Length)

        if ($dateText -notmatch "^\d{6}$") {
            Write-Log "Saltando carpeta con formato no reconocido: $($folder.FullName)" "WARN"
            continue
        }

        try {
            $folderDate = [datetime]::ParseExact(
                $dateText,
                $DateFormat,
                [System.Globalization.CultureInfo]::InvariantCulture
            )

            if ($folderDate.Date -lt $limitDate) {
                Write-Log "Eliminando carpeta antigua de respaldo: $($folder.FullName)"
                Remove-Item -Path $folder.FullName -Recurse -Force
            }
            else {
                Write-Log "Conservando carpeta: $($folder.FullName)"
            }
        }
        catch {
            Write-Log "No se pudo interpretar fecha de carpeta '$($folder.FullName)': $($_.Exception.Message)" "WARN"
        }
    }
}

# ---------------- EXPORTACION ----------------

function Export-RemoteDatabase {
    param(
        [Parameter(Mandatory = $true)]$Station,
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)][string]$TodayDir
    )

    $outputFile = Join-Path $TodayDir $Station.output_file

    if (Test-Path $outputFile) {
        Remove-Item -Path $outputFile -Force
    }

    $sshArgs = @()

    if ($Config.ssh.batch_mode -eq $true) {
        $sshArgs += "-o"
        $sshArgs += "BatchMode=yes"
    }

    if ($Config.ssh.connect_timeout_seconds) {
        $sshArgs += "-o"
        $sshArgs += ("ConnectTimeout={0}" -f [int]$Config.ssh.connect_timeout_seconds)
    }

    # Keepalive para dumps grandes o conexiones inestables.
    $sshArgs += "-o"
    $sshArgs += "ServerAliveInterval=30"
    $sshArgs += "-o"
    $sshArgs += "ServerAliveCountMax=6"

    $sshTarget = "{0}@{1}" -f $Config.ssh.user, $Station.ip
    $remoteCommand = [string]$Config.ssh.remote_command

    Write-Log "Exportando $($Station.name) desde $sshTarget hacia $outputFile"

    $quotedArgs = @("ssh.exe")
    foreach ($arg in $sshArgs) {
        $quotedArgs += (Quote-CmdArg $arg)
    }

    $quotedArgs += (Quote-CmdArg $sshTarget)
    $quotedArgs += (Quote-CmdArg $remoteCommand)

    # STDOUT va al .sql. STDERR va al unico sync.log.
    $cmd = ($quotedArgs -join " ") +
        " 1> " + (Quote-CmdArg $outputFile) +
        " 2>> " + (Quote-CmdArg $script:MainLog)

    Invoke-CmdLine -CommandLine $cmd -StepName "Exportacion SSH de $($Station.name)" | Out-Null

    if (-not (Test-Path $outputFile)) {
        throw "No se genero archivo SQL para $($Station.name): $outputFile"
    }

    $fileInfo = Get-Item $outputFile

    if ($fileInfo.Length -le 0) {
        throw "El archivo SQL de $($Station.name) esta vacio: $outputFile"
    }

    Write-Log "Exportacion OK de $($Station.name). Tamano: $([math]::Round($fileInfo.Length / 1MB, 2)) MB"

    return $outputFile
}

# ---------------- IMPORTACION ----------------

function Import-ToCentralDatabase {
    param(
        [Parameter(Mandatory = $true)]$Station,
        [Parameter(Mandatory = $true)][string]$InputFile,
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)][string]$AddToCentralScript,
        [Parameter(Mandatory = $true)][string]$TempDir
    )

    $transformSql = Join-Path $TempDir ("{0}_centralized.sql" -f $Station.name)

    if (Test-Path $transformSql) {
        Remove-Item -Path $transformSql -Force
    }

    Write-Log "Transformando $($Station.name) con add_to_database_central.py..."

    # STDOUT del python va al SQL centralizado temporal.
    # STDERR del python va al unico sync.log.
    $transformCmd = "py " +
        (Quote-CmdArg $AddToCentralScript) +
        " --input " +
        (Quote-CmdArg $InputFile) +
        " --source-station " +
        (Quote-CmdArg ([string]$Station.name)) +
        " 1> " +
        (Quote-CmdArg $transformSql) +
        " 2>> " +
        (Quote-CmdArg $script:MainLog)

    Invoke-CmdLine -CommandLine $transformCmd -StepName "Transformacion de $($Station.name)" | Out-Null

    if (-not (Test-Path $transformSql)) {
        throw "No se genero SQL centralizado para $($Station.name): $transformSql"
    }

    $transformInfo = Get-Item $transformSql

    if ($transformInfo.Length -le 0) {
        throw "El SQL centralizado de $($Station.name) esta vacio."
    }

    Write-Log "Importando $($Station.name) hacia PostgreSQL central..."

    # Entrada del psql viene del SQL temporal.
    # STDOUT y STDERR de psql van al unico sync.log.
    $dockerCmd = "docker exec -i " +
        (Quote-CmdArg ([string]$Config.postgres.docker_container)) +
        " psql -v ON_ERROR_STOP=1 -U " +
        (Quote-CmdArg ([string]$Config.postgres.user)) +
        " -d " +
        (Quote-CmdArg ([string]$Config.postgres.database)) +
        " < " +
        (Quote-CmdArg $transformSql) +
        " 1>> " +
        (Quote-CmdArg $script:MainLog) +
        " 2>&1"

    Invoke-CmdLine -CommandLine $dockerCmd -StepName "Importacion PostgreSQL de $($Station.name)" | Out-Null

    Write-Log "Importacion OK de $($Station.name)."

    if (Test-Path $transformSql) {
        Remove-Item -Path $transformSql -Force
    }
}

# ---------------- CONTEOS ----------------

function Show-CentralCounts {
    param(
        [Parameter(Mandatory = $true)]$Config
    )

    $targetTable = [string]$Config.postgres.target_table
    $sourceColumn = [string]$Config.postgres.source_station_column

    if (-not $targetTable) {
        Write-Log "No se configuro postgres.target_table. Saltando conteo final." "WARN"
        return
    }

    Write-Log "Conteo total en $targetTable"

    $countCmd = "docker exec -i " +
        (Quote-CmdArg ([string]$Config.postgres.docker_container)) +
        " psql -U " +
        (Quote-CmdArg ([string]$Config.postgres.user)) +
        " -d " +
        (Quote-CmdArg ([string]$Config.postgres.database)) +
        " -c " +
        (Quote-CmdArg "SELECT COUNT(*) AS total_central FROM $targetTable;") +
        " 1>> " +
        (Quote-CmdArg $script:MainLog) +
        " 2>&1"

    Invoke-CmdLine -CommandLine $countCmd -StepName "Conteo total" | Out-Null

    if ($sourceColumn) {
        Write-Log "Conteo por $sourceColumn en $targetTable"

        $countStationCmd = "docker exec -i " +
            (Quote-CmdArg ([string]$Config.postgres.docker_container)) +
            " psql -U " +
            (Quote-CmdArg ([string]$Config.postgres.user)) +
            " -d " +
            (Quote-CmdArg ([string]$Config.postgres.database)) +
            " -c " +
            (Quote-CmdArg "SELECT $sourceColumn, COUNT(*) AS total FROM $targetTable GROUP BY $sourceColumn ORDER BY $sourceColumn;") +
            " 1>> " +
            (Quote-CmdArg $script:MainLog) +
            " 2>&1"

        Invoke-CmdLine -CommandLine $countStationCmd -StepName "Conteo por estacion" | Out-Null
    }
}

# ---------------- EJECUCION PRINCIPAL ----------------

$script:MainLog = $null
$okCount = 0
$errorCount = 0
$skippedCount = 0

try {
    $Config = Load-Config -Path $ConfigPath
    Test-Config -Config $Config

    $BaseSyncDir = [string]$Config.paths.base_sync_dir
    $AddToCentralScript = Resolve-PathFromScriptRoot -PathValue ([string]$Config.paths.add_to_central_script)

    $FolderPrefix = [string]$Config.retention.folder_prefix
    $DateFormat = [string]$Config.retention.date_format
    $TodayFolderName = "{0}{1}" -f $FolderPrefix, (Get-Date -Format $DateFormat)
    $TodayDir = Join-Path $BaseSyncDir $TodayFolderName
    $LogDir = Join-Path $TodayDir ([string]$Config.paths.logs_folder_name)
    $TempDir = Join-Path $TodayDir "_temp"

    New-Item -ItemType Directory -Force -Path $BaseSyncDir | Out-Null
    New-Item -ItemType Directory -Force -Path $TodayDir | Out-Null
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

    $script:MainLog = Join-Path $LogDir "sync.log"

    Write-Log "============================================================"
    Write-Log "Iniciando FTS DWH Sync desde JSON"
    Write-Log "ConfigPath: $ConfigPath"
    Write-Log "Carpeta diaria: $TodayDir"
    Write-Log "Script centralizador: $AddToCentralScript"
    Write-Log "Log unico: $script:MainLog"
    Write-Log "============================================================"

    Assert-CommandExists -CommandName "ssh"
    Assert-CommandExists -CommandName "docker"
    Assert-CommandExists -CommandName "py"

    if (-not (Test-Path $AddToCentralScript)) {
        throw "No se encontro add_to_database_central.py en: $AddToCentralScript"
    }

    foreach ($station in $Config.stations) {
        if ($station.enabled -eq $false) {
            $skippedCount++
            Write-Log "Saltando estacion deshabilitada: $($station.name)" "WARN"
            continue
        }

        try {
            Write-Log "------------------------------------------------------------"
            Write-Log "Procesando estacion: $($station.name)"

            $sqlFile = Export-RemoteDatabase `
                -Station $station `
                -Config $Config `
                -TodayDir $TodayDir

            Import-ToCentralDatabase `
                -Station $station `
                -InputFile $sqlFile `
                -Config $Config `
                -AddToCentralScript $AddToCentralScript `
                -TempDir $TempDir

            $okCount++
            Write-Log "Finalizado OK: $($station.name)"
        }
        catch {
            $errorCount++
            Write-Log "ERROR en $($station.name): $($_.Exception.Message)" "ERROR"
            continue
        }
    }

    Write-Log "------------------------------------------------------------"
    Write-Log "Resumen estaciones OK: $okCount | Error: $errorCount | Saltadas: $skippedCount"

    Show-CentralCounts -Config $Config

    # Limpieza de temporales
    if (Test-Path $TempDir) {
        Remove-Item -Path $TempDir -Recurse -Force
    }

    if ($Config.retention.enabled -eq $true) {
        Remove-OldDatabaseFolders `
            -BaseSyncDir $BaseSyncDir `
            -FolderPrefix $FolderPrefix `
            -DateFormat $DateFormat `
            -RetentionDays ([int]$Config.retention.days)
    }
    else {
        Write-Log "Retencion deshabilitada desde JSON."
    }

    Write-Log "============================================================"
    Write-Log "FTS DWH Sync terminado"
    Write-Log "============================================================"

    if ($errorCount -gt 0) {
        exit 2
    }
}
catch {
    Write-Log "ERROR GENERAL: $($_.Exception.Message)" "ERROR"
    exit 1
}
