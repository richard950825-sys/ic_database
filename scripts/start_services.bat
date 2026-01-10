@echo off
echo [INFO] Checking Docker status...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

echo [INFO] Cleaning up old containers (if any)...
docker rm -f qdrant_db >nul 2>&1
docker rm -f neo4j_db >nul 2>&1
echo [INFO] Old containers removed.

echo [INFO] Starting Qdrant Vector Database...
REM Volume mapped to local qdrant_data folder for persistence
if not exist "qdrant_data" mkdir "qdrant_data"
docker run -d -p 6333:6333 -v "%cd%\qdrant_data":/qdrant/storage --name qdrant_db qdrant/qdrant

echo [INFO] Starting Neo4j Graph Database...
REM Mapping:
REM - HTTP: 17474 -> 7474 (High port avoids reservation)
REM - Bolt: 17687 -> 7687 (High port avoids reservation)
REM - Volume mapped to local neo4j_data folder for persistence
if not exist "neo4j_data" mkdir "neo4j_data"
docker run -d -p 17474:7474 -p 17687:7687 -v "%cd%\neo4j_data":/data --name neo4j_db -e NEO4J_AUTH=neo4j/password123 neo4j

echo.
echo [SUCCESS] Services restarted with SAFE HIGH PORT configuration and DATA PERSISTENCE.
echo - Qdrant: http://localhost:6333
echo - Neo4j Browser: http://localhost:17474
echo - Neo4j Bolt: bolt://localhost:17687
echo.
pause
