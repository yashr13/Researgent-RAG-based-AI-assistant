@echo off
REM Quick start script for RAG Assistant with PostgreSQL (Windows)

echo.
echo 🚀 RAG Assistant - PostgreSQL Setup
echo ====================================

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker is not installed. Please install Docker.
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Compose is not installed. Please install Docker Compose.
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo 📝 Creating .env file from template...
    copy .env.example .env
    echo.
    echo ⚠️  Please update .env with your configuration, especially:
    echo    - OPENAI_API_KEY
    echo    - DB_PASSWORD (use a strong password)
    echo.
    echo Edit .env and run this script again.
    pause
    exit /b 0
)

echo ✅ .env file found
echo.

REM Start services
echo 🐳 Starting Docker containers...
docker-compose up -d

echo.
echo ⏳ Waiting for services to be ready (30 seconds)...
timeout /t 30 /nobreak

REM Check service health
echo.
echo 🔍 Checking service status...
docker-compose ps

REM Initialize database
echo.
echo 🗄️  Initializing database...
docker-compose exec -T backend python -c "from app.db import init_db; init_db()"
echo ✅ Database initialized

REM Summary
echo.
echo ==================================
echo ✅ Setup Complete!
echo ==================================
echo.
echo Services running:
echo   📊 PostgreSQL: localhost:5432
echo   🔍 Chroma: http://localhost:8001
echo   🔗 Backend API: http://localhost:8000
echo.
echo Next steps:
echo   1. Set up frontend: cd frontend ^&^& npm install ^&^& npm run build
echo   2. Visit API docs: http://localhost:8000/docs
echo.
echo Useful commands:
echo   docker-compose logs -f backend    # View backend logs
echo   docker-compose ps                 # Check service status
echo   docker-compose down               # Stop services
echo.
pause
