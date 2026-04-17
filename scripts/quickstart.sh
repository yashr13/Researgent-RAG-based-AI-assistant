#!/bin/bash
# Quick start script for RAG Assistant with PostgreSQL

set -e

echo "🚀 RAG Assistant - PostgreSQL Setup"
echo "===================================="

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env with your configuration, especially:"
    echo "   - OPENAI_API_KEY"
    echo "   - DB_PASSWORD (use a strong password)"
    echo ""
    echo "Edit .env and run this script again."
    exit 0
fi

echo "✅ .env file found"

# Start services
echo "🐳 Starting Docker containers..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready (30 seconds)..."
sleep 30

# Check service health
echo ""
echo "🔍 Checking service status..."
docker-compose ps

# Initialize database
echo ""
echo "🗄️  Initializing database..."
docker-compose exec -T backend python -c "from app.db import init_db; init_db()"
echo "✅ Database initialized"

# Summary
echo ""
echo "=================================="
echo "✅ Setup Complete!"
echo "=================================="
echo ""
echo "Services running:"
echo "  📊 PostgreSQL: localhost:5432"
echo "  🔍 Chroma: http://localhost:8001"
echo "  🔗 Backend API: http://localhost:8000"
echo ""
echo "Next steps:"
echo "  1. Set up frontend: cd frontend && npm install && npm run build"
echo "  2. Visit API docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  docker-compose logs -f backend    # View backend logs"
echo "  docker-compose ps                 # Check service status"
echo "  docker-compose down               # Stop services"
echo ""
