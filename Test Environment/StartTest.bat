@echo off
setlocal enabledelayedexpansion

rem 保存当前目录
set "pwdn=%cd%"

set "mode=%~1"
set "build_dir=%pwdn%\builds"
if /i "%mode%"=="server" (
    set "build_dir=%build_dir%\server"
) else if /i "%mode%"=="client" (
    set "build_dir=%build_dir%\client"
)

if not exist "%build_dir%" (
    mkdir "%build_dir%"
)

del /q "%build_dir%\ConnectCore-*.pyz" >nul 2>&1

pushd ..
if errorlevel 1 (
    echo 无法切换到上级目录。
    exit /b 1
)

python -m mcdreforged pack -o "%build_dir%"
set "pack_result=%errorlevel%"
popd
if not "%pack_result%"=="0" (
    echo 打包失败，错误码: %pack_result%
    exit /b %pack_result%
)

pushd "%build_dir%"
if errorlevel 1 (
    echo 无法进入 builds 目录。
    exit /b 1
)

set "pyz_file="
for %%F in ("ConnectCore-*.pyz") do (
    set "pyz_file=%%~fF"
    goto run_pyz
)

echo 未找到 ConnectCore-*.pyz
popd
exit /b 1

:run_pyz
python "%pyz_file%" %*
set "run_result=%errorlevel%"
popd
exit /b %run_result%
