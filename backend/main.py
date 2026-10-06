import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quantum_city")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    from database.database import Base, engine
    import database.models  # registers ORM models with Base
    Base.metadata.create_all(bind=engine)
    logger.info("Quantum City database tables initialized.")
    logger.info("Quantum City backend has started successfully.")
    yield
    logger.info("Quantum City backend is shutting down.")


app = FastAPI(
    title="Quantum City Backend",
    description="Backend API for Quantum City Metaverse simulation and optimization.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration for Unity and frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
from api.worlds import router as worlds_router
from api.simulation import router as simulation_router
from api.prediction import router as prediction_router
from api.optimization import router as optimization_router
from api.analytics import router as analytics_router

app.include_router(worlds_router)
app.include_router(simulation_router)
app.include_router(prediction_router)
app.include_router(optimization_router)
app.include_router(analytics_router)


@app.get("/")
def read_root():
    return {
        "message": "Quantum City backend is running",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "quantum-city-backend",
    }
