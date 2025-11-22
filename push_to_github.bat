@echo off
REM =========================================================
REM Git Push Script for Edge Mini-K8s
REM Repository: https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration
REM =========================================================

echo.
echo ====================================
echo Edge Mini-K8s - Git Push Script
echo ====================================
echo.

REM Navigate to project directory
cd /d "%~dp0"

REM Check if git is initialized
if not exist ".git" (
    echo Initializing Git repository...
    git init
    git remote add origin https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration.git
    echo Git repository initialized!
    echo.
)

REM Check if remote exists, if not add it
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo Adding remote origin...
    git remote add origin https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration.git
)

echo Checking repository status...
echo.
git status
echo.

REM Add all files (respecting .gitignore)
echo Adding files to staging area...
git add .
echo Done!
echo.

REM Prompt for commit message
set /p commit_msg="Enter commit message (or press Enter for default): "
if "%commit_msg%"=="" set commit_msg=Update Edge Mini-K8s project

REM Commit changes
echo.
echo Committing changes...
git commit -m "%commit_msg%"

if errorlevel 1 (
    echo.
    echo No changes to commit or commit failed.
    echo.
    pause
    exit /b 1
)

REM Ask if user wants to push
echo.
set /p push_confirm="Push to GitHub? (Y/N): "
if /i not "%push_confirm%"=="Y" (
    echo Push cancelled by user.
    echo Changes are committed locally but not pushed to GitHub.
    pause
    exit /b 0
)

REM Pull latest changes first (in case of conflicts)
echo.
echo Pulling latest changes from remote...
git pull origin master --rebase

if errorlevel 1 (
    echo.
    echo WARNING: Pull failed. There might be conflicts.
    echo Please resolve conflicts manually and run this script again.
    echo.
    pause
    exit /b 1
)

REM Push to GitHub
echo.
echo Pushing to GitHub...
git push -u origin master

if errorlevel 1 (
    echo.
    echo WARNING: Push failed!
    echo.
    echo Common reasons:
    echo 1. Authentication required - Set up Personal Access Token
    echo 2. Remote has changes - Pull first with: git pull origin master
    echo 3. Branch name mismatch - Check branch with: git branch
    echo.
    echo To set up authentication:
    echo 1. Go to GitHub Settings ^> Developer Settings ^> Personal Access Tokens
    echo 2. Generate new token with 'repo' scope
    echo 3. Use token as password when prompted
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================
echo SUCCESS! 🎉
echo ====================================
echo.
echo Your changes have been pushed to:
echo https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration
echo.
echo You can view your repository at:
echo https://github.com/Aditya-Ithamraju/Lightweight_container_orchestration
echo.
pause
